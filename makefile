
test:
	export PYTHONPATH="./src/Spiders/"&& python `find ./testc/ -name *Test.py`

dev:
	- rm -rf Mongo2.docset
	python ./src/main.py http://api.mongodb.com/java/2.0/overview-summary.html Mongo2
