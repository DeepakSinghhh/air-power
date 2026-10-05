"""Convert the percent-format sources in this folder into Colab notebooks:  python src/build_notebooks.py"""
import json
import pathlib
import re

HERE = pathlib.Path(__file__).parent


def convert(src: pathlib.Path) -> dict:
    cells = []
    for chunk in re.split(r"^# %%", src.read_text(), flags=re.M):
        if not chunk.strip():
            continue
        if chunk.startswith(" [markdown]"):
            lines = chunk.split("\n", 1)[1].splitlines()
            text = "\n".join(l[2:] if l.startswith("# ") else l.lstrip("#") for l in lines).strip()
            cells.append({"cell_type": "markdown", "metadata": {}, "source": text.splitlines(keepends=True)})
        else:
            code = chunk.split("\n", 1)[1].strip("\n")
            cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
                          "source": code.splitlines(keepends=True)})
    return {"cells": cells, "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"},
                         "accelerator": "GPU", "colab": {"provenance": []}}}


for src in sorted(HERE.glob("0*.py")):
    out = HERE.parent / (src.stem + ".ipynb")
    out.write_text(json.dumps(convert(src), indent=1))
    print("wrote", out.name)
