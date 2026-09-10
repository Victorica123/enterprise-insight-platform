# 前端镜像：Node 构建 + nginx 托管静态文件并反代 /api 到后端
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# 容器内同源部署：Agent 与 Media 使用独立前缀，统一由 nginx 反代。
ARG VITE_API_BASE_URL=/agent
ARG VITE_MEDIA_API_BASE_URL=/media
ARG VITE_OIDC_ENABLED=false
ARG VITE_OIDC_ISSUER=
ARG VITE_OIDC_CLIENT_ID=enterprise-insight-web
ARG VITE_LOCAL_AUTH_ENABLED=true
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_MEDIA_API_BASE_URL=$VITE_MEDIA_API_BASE_URL
ENV VITE_OIDC_ENABLED=$VITE_OIDC_ENABLED
ENV VITE_OIDC_ISSUER=$VITE_OIDC_ISSUER
ENV VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID
ENV VITE_LOCAL_AUTH_ENABLED=$VITE_LOCAL_AUTH_ENABLED
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
