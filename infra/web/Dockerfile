FROM node:24.16.0-alpine3.22 AS build

WORKDIR /workspace
RUN npm install --global pnpm@11.19.0
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/package.json
RUN pnpm install --frozen-lockfile
COPY frontend/ frontend/
RUN pnpm --filter @dnf-leader/frontend build

FROM nginx:1.29.1-alpine3.22
COPY infra/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /workspace/frontend/dist /usr/share/nginx/html
EXPOSE 80
