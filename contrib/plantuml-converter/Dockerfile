FROM snakepacker/python:all as builder

RUN apt-get update && apt-get install -y wget

ENV PLANTUML_VERSION 1.2019.5
RUN python3.7 -m venv /usr/share/python3/app
RUN wget \
    https://sourceforge.net/projects/plantuml/files/plantuml.${PLANTUML_VERSION}.jar/download \
    -O /usr/share/python3/app/bin/plantuml.jar

###############################################################################
FROM snakepacker/python:3.7
RUN apt-get update && apt-get install -y openjdk-8-jre-headless graphviz && apt-get clean

ENV PATH=/usr/share/python3/app/bin:$PATH
ENV PLANTUML_JAR=/usr/share/python3/app/bin/plantuml.jar

COPY --from=builder /usr/share/python3/app /usr/share/python3/app
COPY convert.py /usr/local/bin/convert
RUN chmod a+x /usr/local/bin/convert

ENTRYPOINT ["/usr/local/bin/convert"]
