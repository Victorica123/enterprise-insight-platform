# 前端镜像：Node 构建 + nginx 托管静态文件并反代 /api 到后端
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# 容器内同源部署：Agent 与 Media 使用独立前缀，统一由 nginx 反代。
ARG VITE_API_BASE_URL=/agent
ARG VITE_MEDIA_API_BASE_URL=/media
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
ENV VITE_MEDIA_API_BASE_URL=$VITE_MEDIA_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
