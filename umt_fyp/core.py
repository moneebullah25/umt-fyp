# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/00_core.ipynb.

# %% auto 0
__all__ = ['data', 'chars', 'data_size', 'vocab_size', 'char_to_ix', 'ix_to_char']

# %% ../nbs/00_core.ipynb 5
data = open('shakespeare.txt', 'r').read()
data= data.lower()
chars = list(set(data))
data_size, vocab_size = len(data), len(chars)
data_size, vocab_size

# %% ../nbs/00_core.ipynb 7
chars = sorted(chars)
chars

# %% ../nbs/00_core.ipynb 9
char_to_ix = { ch:i for i,ch in enumerate(chars) }
ix_to_char = { i:ch for i,ch in enumerate(chars) }
ix_to_char