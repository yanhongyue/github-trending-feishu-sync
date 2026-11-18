PYTHON ?= python3
PKG = github_trending_sync

.PHONY: install sync collect report

## 安装依赖与浏览器
install:
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m playwright install chromium

## 一键运行：采集 + 写库 + 发日报
sync:
	$(PYTHON) -m $(PKG) sync

## 仅采集验证
collect:
	$(PYTHON) -m $(PKG) collect

## 仅按当天记录发送日报（人工复核后补发）
report:
	$(PYTHON) -m $(PKG) report
