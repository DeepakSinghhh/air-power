# Vendored public datasets

Copies of the two public datasets TATPAR trains on, so `make train` works offline and does not depend
on the original download links staying up. The loaders use these first and fall back to the source URL.

| File | Source | Licence / terms | SHA-256 |
|---|---|---|---|
| `cmapss_txt.tar.xz` — `train_/test_/RUL_FD001–FD004.txt`, `readme.txt` | NASA Prognostics Center of Excellence, "Turbofan Engine Degradation Simulation Data Set" (A. Saxena, K. Goebel, 2008), [download used by the loader](https://phm-datasets.s3.amazonaws.com/NASA/6.+Turbofan+Engine+Degradation+Simulation+Data+Set.zip) | Publicly released by NASA; cite Saxena et al., "Damage Propagation Modeling for Aircraft Engine Run-to-Failure Simulation", PHM 2008. The paper PDF from the original archive is not redistributed here. | `5dce94ce…a830159` |
| `maintnet/maintnet_aviation_dataset_deidentified.csv`, `maintnet/aviation_abbriviation.csv` | MaintNet (F. Akhbardeh, T. Desell, M. Zampieri, COLING 2020), [project page](https://people.rit.edu/fa3019/MaintNet/) | [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/): attribution as above; these files are shared under the same licence | `a70daa27…`, `d2f525f4…` |

These files are unmodified (the C-MAPSS text files are repackaged from the NASA zip without changes).
