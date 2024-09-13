FROM python:3.11
EXPOSE 8088
WORKDIR /app
COPY requirements.txt ./
RUN pip install -r requirements.txt
COPY . ./
ENTRYPOINT [ "streamlit", "run", "honne-enterprise.py", "--server.port=8088", "--server.address=0.0.0.0" ]