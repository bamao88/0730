FROM debian:trixie-20260623-slim@sha256:28de0877c2189802884ccd20f15ee41c203573bd87bb6b883f5f46362d24c5c2

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=zh_CN.UTF-8 \
    LC_ALL=zh_CN.UTF-8 \
    SAL_USE_VCLPLUGIN=svp

ARG DOCFIT_APT_MIRROR=http://deb.debian.org
ARG DOCFIT_SECURITY_MIRROR=http://deb.debian.org/debian-security

RUN sed -i \
        -e "s|http://deb.debian.org/debian-security|${DOCFIT_SECURITY_MIRROR}|" \
        -e "s|http://deb.debian.org|${DOCFIT_APT_MIRROR}|" \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
        fontconfig \
        fonts-arphic-gbsn00lp \
        fonts-arphic-gkai00mp \
        fonts-arphic-ukai \
        fonts-arphic-uming \
        fonts-dejavu-core \
        fonts-liberation \
        fonts-noto-cjk \
        fonts-noto-color-emoji \
        fonts-stix \
        libreoffice-writer-nogui \
        locales \
        poppler-utils \
    && sed -i 's/^# *zh_CN.UTF-8 UTF-8/zh_CN.UTF-8 UTF-8/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

COPY 99-docfit-font-substitutions.conf /etc/fonts/conf.d/99-docfit-font-substitutions.conf
COPY packages.lock /opt/docfit/packages.lock

RUN fc-cache -f \
    && soffice --version > /opt/docfit/libreoffice-version.txt \
    && grep -Fx 'LibreOffice 25.2.3.2 520(Build:2)' /opt/docfit/libreoffice-version.txt \
    && while IFS=' ' read -r package expected; do \
         actual="$(dpkg-query -W -f='${Version}' "$package")"; \
         test "$actual" = "$expected" || { \
           echo "$package: expected $expected, found $actual" >&2; exit 1; \
         }; \
       done < /opt/docfit/packages.lock \
    && dpkg-query -W > /opt/docfit/package-versions.txt

WORKDIR /work
