# ---- Stage 1: build the React app ----
# Using a full Node image here (has npm, build tools) -- this layer is
# discarded after build, so its size doesn't affect the final image.
FROM node:20-alpine AS build

WORKDIR /app

# Copy only package files first -- this is the layer-caching trick from
# our Docker fundamentals discussion: dependencies change far less often
# than source code, so `npm install` gets cached and skipped on rebuilds
# that only touch src/.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .
RUN npm run build

# ---- Stage 2: serve the built static files with nginx ----
# Multi-stage build: the final image contains ONLY nginx + the compiled
# static files, not Node.js, not node_modules, not source code. This is
# a big image-size and attack-surface reduction.
FROM nginx:1.27-alpine

COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000

CMD ["nginx", "-g", "daemon off;"]
