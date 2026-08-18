FROM node:24.16.0-alpine3.22 AS build

WORKDIR /workspace
RUN npm install --global pnpm@11.19.0
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/package.json
RUN pnpm install --frozen-lockfile
COPY frontend/ frontend/
ARG VITE_SHOW_DEV_LOGIN=false
ARG VITE_DEV_LOGIN_ACCOUNT
ARG VITE_DEV_LOGIN_CODE
ENV VITE_SHOW_DEV_LOGIN=$VITE_SHOW_DEV_LOGIN
ENV VITE_DEV_LOGIN_ACCOUNT=$VITE_DEV_LOGIN_ACCOUNT
ENV VITE_DEV_LOGIN_CODE=$VITE_DEV_LOGIN_CODE
RUN pnpm --filter @dnf-leader/frontend build

FROM nginx:1.29.1-alpine3.22
COPY infra/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/frontend/dist /usr/share/nginx/html
EXPOSE 80
