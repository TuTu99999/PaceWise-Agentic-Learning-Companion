FROM node:22-alpine AS builder

WORKDIR /app

COPY frontend/pacewise/package.json frontend/pacewise/package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY frontend/pacewise/ .
ARG VITE_API_URL=/api/v1
ARG VITE_LMS_URL=
ARG VITE_LMS_WEB_ENABLED=false
ARG VITE_COURSE_SOURCE_MODE=standalone
ARG VITE_COURSE_PDF_MAX_MB=50
ENV VITE_API_URL=${VITE_API_URL}
ENV VITE_LMS_URL=${VITE_LMS_URL}
ENV VITE_LMS_WEB_ENABLED=${VITE_LMS_WEB_ENABLED}
ENV VITE_COURSE_SOURCE_MODE=${VITE_COURSE_SOURCE_MODE}
ENV VITE_COURSE_PDF_MAX_MB=${VITE_COURSE_PDF_MAX_MB}
RUN npm run build

FROM nginx:1.30.5-alpine3.24@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94

# Apply repository security fixes that may be newer than the immutable base
# layer while keeping the runtime on the pinned Alpine release line. Keep the
# explicit expat floor so a cached upgrade layer cannot reintroduce CVE-2026-77214.
RUN apk upgrade --no-cache \
    && apk add --no-cache 'expat>=2.9.0-r0'

COPY frontend/pacewise/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html
COPY landingpage/ /usr/share/nginx/html/

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1/ || exit 1
