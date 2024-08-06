FROM python:3.12.1
WORKDIR /code

ADD requirements.txt /code
RUN pip install -r requirements.txt

ADD . /code
CMD ["python", "server.py"]
