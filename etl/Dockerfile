###############################
# BASE IMAGE FOR OTHER STAGES
###############################

FROM rootproject/root:6.30.02-ubuntu22.04 AS base

# The ROOT installed in the base image was compiled against python3 in ubuntu22.04 base image
# ROOT's team just installed the latest python version (3.10.x) at build time
#
# So in order to control python version (same as development version)
# we are going to install python 3.10.13 manually
#
# Note: Using this base image we can't change python's minor version
# since root is pre-compiled for python 3.10.x, i.e. we should compile root manually
# for a different python minor version if we need a different minor version
ARG PYTHON_VERSION=3.10.13

RUN wget https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz \
    && tar xzvf Python-${PYTHON_VERSION}.tgz \
    && rm Python-${PYTHON_VERSION}.tgz \
    && cd Python-${PYTHON_VERSION} \
    && ./configure \
    && make -j$(( $(getconf _NPROCESSORS_ONLN) - 2 )) \
    && make install \
    && cd .. \
    && rm -rf Python-${PYTHON_VERSION}

# PYTHONDONTWRITEBYTECODE: Prevents Python from writing pyc files to disc
# PYTHONUNBUFFERED: Prevents Python from buffering stdout and stderr
ENV PYTHONFAULTHANDLER=1 \
  PYTHONUNBUFFERED=1 \
  PYTHONHASHSEED=random \
  PIP_NO_CACHE_DIR=off \
  PIP_DISABLE_PIP_VERSION_CHECK=on \
  PIP_DEFAULT_TIMEOUT=100 \
  POETRY_VERSION=1.7.1

###############################
# BUILDER IMAGE
###############################

FROM base AS builder

WORKDIR /usr/src/app

RUN pip3 install --upgrade pip
RUN pip3 install "poetry==$POETRY_VERSION"

COPY pyproject.toml /usr/src/app/
COPY *poetry.lock /usr/src/app/

RUN poetry export --with=etl,dev --format=requirements.txt > requirements.txt
RUN pip3 wheel --no-cache-dir --no-deps --wheel-dir /usr/src/app/wheels -r requirements.txt

###############################
# FINAL IMAGE
###############################

FROM base

ARG UID=1000
ARG GID=1000

ENV USERNAME=app
ENV HOME=/home/$USERNAME
ENV APP_HOME=$HOME/etl

RUN mkdir -p $HOME
RUN mkdir $APP_HOME
RUN groupadd --system $USERNAME --gid $GID && adduser --system --group $USERNAME --uid $UID

WORKDIR $APP_HOME

RUN apt-get update && apt-get install -y --no-install-recommends netcat python3-gdbm
COPY --from=builder /usr/src/app/wheels /wheels
COPY --from=builder /usr/src/app/requirements.txt .
RUN pip3 install --upgrade pip
RUN pip3 install --no-cache /wheels/*

COPY etl $APP_HOME

RUN chown -R $USERNAME:$USERNAME $APP_HOME

USER $USERNAME
