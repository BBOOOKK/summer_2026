PYTHON ?= python3
PDFLATEX ?= pdflatex
PACKAGE := 24020036035_ShuyuLi_Lab4

.PHONY: all experiments figures report

all: report

experiments:
	$(PYTHON) "$(PACKAGE)/person task/experiments/run_experiments.py"
	$(PYTHON) "$(PACKAGE)/person task/experiments/extended_analysis.py"

figures:
	$(PYTHON) "$(PACKAGE)/person task/experiments/plot_icra.py"
	$(PYTHON) "$(PACKAGE)/person task/experiments/extended_analysis.py" --plots-only
	$(PYTHON) "$(PACKAGE)/person task/experiments/plot_team_results.py"

report: figures
	mkdir -p "$(PACKAGE)/report/build"
	cd "$(PACKAGE)/report/source" && $(PDFLATEX) -interaction=nonstopmode -halt-on-error -output-directory=../build main.tex
	cd "$(PACKAGE)/report/source" && $(PDFLATEX) -interaction=nonstopmode -halt-on-error -output-directory=../build main.tex
	cp "$(PACKAGE)/report/build/main.pdf" "$(PACKAGE)/24020036035_ShuyuLi_LAB4_Report.pdf"
