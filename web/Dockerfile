FROM node:26-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# Caddy serves the app and passes /api to the McLender API. Set SITE_ADDRESS to a domain for automatic HTTPS.
FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/dist /srv
