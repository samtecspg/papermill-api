FROM jupyter/datascience-notebook
WORKDIR /home/papermill_api
COPY requirements.txt /home/papermill_api/requirements.txt
RUN pip install -r requirements.txt
EXPOSE 5000
COPY migrations migrations
COPY papermill_api.py boot.sh ./
USER root
RUN ["chmod", "+x", "boot.sh"]
ENTRYPOINT ["./boot.sh"]

