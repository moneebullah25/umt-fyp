# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_transformers.ipynb.

# %% auto 0
__all__ = ['MultiHeadAttention', 'TransformerLayer', 'Encoder', 'DecoderLayer', 'Decoder', 'Transformer']

# %% ../nbs/00_transformers.ipynb 13
import numpy as np
import pandas as pd
import os
import torch
import torch.nn as nn

# %% ../nbs/00_transformers.ipynb 15
class MultiHeadAttention(nn.Module):
    def __init__(self, embed_size, heads):
        super(MultiHeadAttention, self).__init__()
        """
        MultiHeadAttention mechanism. The input of the MultiHeadAttention mechanism is an embedding (or sequence of embeddings).
        The embeddings are split into different parts and each part is fed into a head.
        :param embed_size: the size of the embedding.
        :param heads: the number of heads you wish to create.
        """
        self.embed_size = embed_size # 512 in Transformer  
        self.heads = heads # 8 in Transformer
        self.head_dim = embed_size // heads # 64 in Transformer
        assert (
            self.head_dim * heads == embed_size
        ), "Embedding size needs to be divisible by heads"
        # === Project Embeddings into three vectors: Query, Key and Value ===
        # Note: some implementations do: nn.Linear(embed_size, head_dim). We won't do this. We will project it 
        # on a space of size embed_size and then split it into N heads of head_dim shape.
        self.values = nn.Linear(embed_size, embed_size)
        self.keys = nn.Linear(embed_size, embed_size)
        self.queries = nn.Linear(embed_size, embed_size)
        self.fc_out = nn.Linear(embed_size, embed_size)

    def forward(self, values, keys, query, mask):
        # Values, Keys and Queries have size: (batch_size, sequence_len, embedding_size)
        batch_size = query.shape[0]# Get number of training examples/batch size.
        value_len, key_len, query_len = values.shape[1], keys.shape[1], query.shape[1]
        # === Pass through Linear Layer ===
        values = self.values(values)  # (batch_size, value_len, embed_size)
        keys = self.keys(keys)  # (batch_size, key_len, embed_size)
        queries = self.queries(query)  # (batch_size, query_len, embed_size)

        # Split the embedding into self.heads different pieces
        values = values.reshape(batch_size, value_len, self.heads, self.head_dim)
        keys = keys.reshape(batch_size, key_len, self.heads, self.head_dim)
        queries = queries.reshape(batch_size, query_len, self.heads, self.head_dim)

        # Einsum does matrix mult. for query*keys for each training example
        # with every other training example, don't be confused by einsum
        # it's just how I like doing matrix multiplication & bmm

        energy = torch.einsum("nqhd,nkhd->nhqk", [queries, keys])
        # queries shape: (batch_size, query_len, heads, heads_dim),
        # keys shape: (batch_size, key_len, heads, heads_dim)
        # energy: (batch_size, heads, query_len, key_len)

        # Mask padded indices so their weights become 0
        if mask is not None:
            energy = energy.masked_fill(mask == 0, float("-1e20"))

        # Normalize energy values similarly to seq2seq + attention
        # so that they sum to 1. Also divide by scaling factor for
        # better stability
        attention = torch.softmax(energy / (self.embed_size ** (1 / 2)), dim=3) 
        # attention shape: (batch_size, heads, query_len, key_len)
        # values shape: (batch_size, value_len, heads, heads_dim)
        # out after matrix multiply: (batch_size, query_len, heads, head_dim), then
        # we reshape and flatten the last two dimensions.
        out = torch.einsum("nhql,nlhd->nqhd", [attention, values]).reshape(
            batch_size, query_len, self.heads * self.head_dim
        )
        # Linear layer doesn't modify the shape, final shape will be
        # (batch_size, query_len, embed_size)
        out = self.fc_out(out)
        return out

# %% ../nbs/00_transformers.ipynb 17
class TransformerLayer(nn.Module):
    def __init__(self, embed_size, heads, dropout, forward_expansion=4):
        super(TransformerLayer, self).__init__()
        self.attention = MultiHeadAttention(embed_size, heads) 
        self.norm1 = nn.LayerNorm(embed_size)
        self.norm2 = nn.LayerNorm(embed_size)
        self.feed_forward = nn.Sequential(
            nn.Linear(embed_size, forward_expansion * embed_size),
            nn.ReLU(),
            nn.Linear(forward_expansion * embed_size, embed_size),
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, value, key, query, mask):
        # Values, Keys and Queries have size: (batch_size, query_len, embedding_size)
        attention = self.attention(value, key, query, mask) # attention shape: (batch_size, query_len, embedding_size)
        # Add skip connection, run through normalization and finally dropout
        x = self.dropout(self.norm1(attention + query)) # x shape: (batch_size, query_len, embedding_size)
        forward = self.feed_forward(x) # forward shape: (batch_size, query_len, embedding_size)
        out = self.dropout(self.norm2(forward + x)) # out shape: (batch_size, query_len, embedding_size)
        return out

# %% ../nbs/00_transformers.ipynb 19
class Encoder(nn.Module):
    def __init__(self, src_vocab_size, embed_size, num_layers, heads,
        device, forward_expansion, dropout, max_length): 
        super(Encoder, self).__init__()
        self.embed_size = embed_size # size of the input embedding
        self.device = device # either "cuda" or "cpu"
        # Lookup table with an embedding for each word in the vocabulary
        self.word_embedding = nn.Embedding(src_vocab_size, embed_size) 
        # Lookup table with a positional embedding for each word in the sequence
        self.position_embedding = nn.Embedding(max_length, embed_size)
        self.layers = nn.ModuleList(
            [
                TransformerLayer(
                    embed_size,
                    heads,
                    dropout=dropout,
                    forward_expansion=forward_expansion,
                )
                for _ in range(num_layers)
            ]
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, mask):
        """
        Forward pass.
        :param x: source sequence. Shape: (batch_size, source_sequence_len).
        :param mask: source mask is used when we need to pad the input.
        :return output: torch tensor of shape (batch_size, src_sequence_length, embedding_size)
        """
        batch_size, seq_length = x.shape
        # positions is an arange from (0,seq_len), e.g: torch.tensor([[0,1,2,...,N], [0,1,2,...,N], ..., [0,1,2,...,N]])
        positions = torch.arange(0, seq_length).expand(batch_size, seq_length).to(self.device)
        out = self.dropout((self.word_embedding(x) + self.position_embedding(positions)))
        # In the Encoder the query, key, value are all the same, in the
        # decoder this will change. This might look a bit odd in this case.
        for layer in self.layers:
            out = layer(out, out, out, mask)
        # output shape: torch.Size([batch_size, sequence_length, embedding_size])
        return out

# %% ../nbs/00_transformers.ipynb 21
class DecoderLayer(nn.Module):
    def __init__(self, embed_size, heads, forward_expansion, dropout, device):
        super(DecoderLayer, self).__init__()
        self.norm = nn.LayerNorm(embed_size)
        self.attention = MultiHeadAttention(embed_size, heads=heads)
        self.transformer_block = TransformerLayer(
            embed_size, heads, dropout, forward_expansion
        )
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, value, key, src_mask, trg_mask):
        """
        :param x: target input. Shape: (batch_size, target_sequence_len, embedding_size)
        :param value: value extracted from encoder.
        :param key: key extracted from encoder.
        :param src_mask: source mask is used when we need to pad the input.
        :param trg_mask: target mask is used to pass one element of the target at a time.
        """
        
        attention = self.attention(x, x, x, trg_mask)
        query = self.dropout(self.norm(attention + x))
        out = self.transformer_block(value, key, query, src_mask)
        return out

# %% ../nbs/00_transformers.ipynb 23
class Decoder(nn.Module):
    def __init__(self, trg_vocab_size, embed_size, num_layers, heads, forward_expansion,
        dropout, device, max_length):
        """
        :param trg_vocab_size: number of unique tokens in target vocabulary.
        :param embed_size: size of output embeddings.
        :param num_layers: number of DecoderLayers in the Decoder.
        :param heads: number of heads in the MultiAttentionHeads inside the DecoderLayer.
        :param forward_expansion: expansion factor in LinearLayer at the end of the TransformerLayer.
        :param dropout: dropout probability.
        :param device: either "cuda" or "cpu".
        :param max_length: maximum length of sequence.
        """
        super(Decoder, self).__init__()
        self.device = device
        #=== For each token in target vocab there is a token embedding ===
        self.word_embedding = nn.Embedding(trg_vocab_size, embed_size) 
        self.position_embedding = nn.Embedding(max_length, embed_size)
        self.layers = nn.ModuleList(
            [
                DecoderLayer(embed_size, heads, forward_expansion, dropout, device)
                for _ in range(num_layers)
            ]
        )
        self.fc_out = nn.Linear(embed_size, trg_vocab_size)
        self.dropout = nn.Dropout(dropout)

    def forward(self, x, enc_out, src_mask, trg_mask):
        """
        :param x: target sequence. Shape: (batch_size, target_sequence_len)
        :param enc_out: encoder output. Shape: (batch_size, src_sequence_length, embedding_size)
        :param src_mask: source mask.
        :param trg_mask: target mask.
        """
        batch_size, seq_length = x.shape # x shape: (batch_size, target_sequence_len)
        # positions is an arange from (0,seq_len), e.g: torch.tensor([[0,1,2,...,N], [0,1,2,...,N], ..., [0,1,2,...,N]])
        positions = torch.arange(0, seq_length).expand(batch_size, seq_length).to(self.device) # positions shape: (batch_size, target_sequence_len)
        x = self.dropout((self.word_embedding(x) + self.position_embedding(positions)))

        for layer in self.layers:
            x = layer(x, enc_out, enc_out, src_mask, trg_mask)

        out = self.fc_out(x)
        return out

# %% ../nbs/00_transformers.ipynb 25
class Transformer(nn.Module):
    def __init__(self, src_vocab_size, trg_vocab_size, src_pad_idx, trg_pad_idx, embed_size=512,
                 num_layers=6, forward_expansion=4, heads=8, dropout=0, device="cpu", max_length=100):

        super(Transformer, self).__init__()
        # === Encoder ===
        self.encoder = Encoder(src_vocab_size, embed_size, num_layers, heads, device, forward_expansion, dropout, max_length)
        # === Decoder ===
        self.decoder = Decoder(trg_vocab_size, embed_size, num_layers, heads, forward_expansion, dropout, device, max_length)
        self.src_pad_idx = src_pad_idx
        self.trg_pad_idx = trg_pad_idx
        self.device = device

    def make_src_mask(self, src):
        src_mask = (src != self.src_pad_idx).unsqueeze(1).unsqueeze(2)
        # (N, 1, 1, src_len)
        return src_mask.to(self.device)

    def make_trg_mask(self, trg):
        """
        Returns a lower triangular matrix filled with 1s. The shape of the mask is (target_size, target_size).
        Example: for a target of shape (batch_size=1, target_size=4)
        tensor([[[[1., 0., 0., 0.],
                  [1., 1., 0., 0.],
                  [1., 1., 1., 0.],
                  [1., 1., 1., 1.]]]])
        """
        N, trg_len = trg.shape
        trg_mask = torch.tril(torch.ones((trg_len, trg_len))).expand(
            N, 1, trg_len, trg_len
        )
        return trg_mask.to(self.device)

    def forward(self, src, trg):
        src_mask = self.make_src_mask(src) # src_mask shape: 
        trg_mask = self.make_trg_mask(trg) # trg_mask shape: 
        enc_src = self.encoder(src, src_mask) # enc_src shape:
        out = self.decoder(trg, enc_src, src_mask, trg_mask) # out shape: 
        return out
