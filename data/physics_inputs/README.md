# Light-curve inputs for the physical model

Copies of `data/processed/f13_lc_cache/TIC*.npz` for the stars `f26_ebfit.py` fits, so the
model can be rerun anywhere (for example the Physics workflow on GitHub Actions) without
fetching from MAST. Arrays: `t` (BTJD), `f` (flux), `e` (flux error), `sector`.
