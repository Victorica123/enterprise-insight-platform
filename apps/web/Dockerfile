# 前端镜像：Node 构建 + nginx 托管静态文件并反代 /api 到后端
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# 容器内同源部署：API 请求走 nginx /api 反代（本地开发默认 127.0.0.1:8000 不受影响）
ARG VITE_API_BASE_URL=/api
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
