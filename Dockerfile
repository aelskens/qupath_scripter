# Adaptation of https://github.com/qupath/qupath/issues/1839#issuecomment-2804515426 

FROM python:3.13

LABEL maintainer="Arthur Elskens <arthur.elskens@ulb.be>"

# Provide your username and id at build time to match that of the host machine
ARG USERNAME=aelskens
ARG USER_UID=1001
ARG USER_GID=$USER_UID

# Avoid question/dialog when apt-get install
ENV DEBIAN_FRONTEND=noninteractive

# Create user that correspond to the user on the OS
RUN groupadd --gid $USER_GID $USERNAME \
    && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME \
	&& usermod --shell /bin/bash $USERNAME \
    #
    # [Optional] Add sudo support. Omit if you don't need to install software after connecting.
    && apt update \
    && apt install -y sudo \
    && echo $USERNAME ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$USERNAME \
    && chmod 0440 /etc/sudoers.d/$USERNAME

USER $USERNAME
ENV USER_HOME="/home/${USERNAME}"

# Fix ownership issue with the home directory
RUN sudo chown -R ${USERNAME} ${HOME}

RUN sudo apt-get update \
    && sudo apt-get install -y git openjdk-21-jdk binutils

RUN sudo git clone https://github.com/qupath/qupath.git  "/opt/qupath"
RUN cd  "/opt/qupath" \
    && sudo ./gradlew clean jpackage
ENV PATH="/opt/qupath/build/dist/QuPath/bin:$PATH"

# Create and activate a venv
ENV VIRTUAL_ENV="${USER_HOME}/opt/qupath_scripter"
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Ensure the installation of all additional packages. To avoid rebuilding untouched steps
# upon changing the requirements, make sure to keep these at the end of your Dockerfile
COPY requirements.txt /tmp/packages/
RUN pip install -r /tmp/packages/requirements.txt
COPY dev-requirements.txt /tmp/packages/
RUN pip install -r /tmp/packages/dev-requirements.txt

# Clean up
RUN sudo rm -r /tmp/packages