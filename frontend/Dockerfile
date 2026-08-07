# syntax=docker/dockerfile:1
#
# Phase 19A production image for the QueryMind frontend (Phase 18). Builds the existing,
# unmodified Vite app and serves the static output through nginx -- no frontend source changes,
# no behavior changes; this file only packages what `npm run build` already produces.

# --------------------------------------------------------------------------
# Stage 1: builder — install with npm ci (reproducible, lockfile-exact) and
# produce the production Vite build.
# --------------------------------------------------------------------------
FROM node:22-alpine AS builder

WORKDIR /app

# Installed from the lockfile only first, so this layer stays cached across source changes and
# only invalidates when package.json/package-lock.json change.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

# --------------------------------------------------------------------------
# Stage 2: runtime — static files served by nginx, running as a non-root
# user throughout (nginxinc/nginx-unprivileged: no build tooling, no
# node_modules, no source -- only the compiled dist/ output).
# --------------------------------------------------------------------------
FROM nginxinc/nginx-unprivileged:1.27-alpine AS runtime

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

# The unprivileged nginx image already runs as the non-root `nginx` user and listens on 8080
# by default (binding <1024 requires root, which this image deliberately never has).
EXPOSE 8080

# `127.0.0.1`, not `localhost`: nginx's `listen 8080;` binds IPv4 only, but this image's
# /etc/hosts resolves `localhost` to both 127.0.0.1 and ::1, and Alpine's musl libc prefers the
# IPv6 result (RFC 6724) regardless of /etc/hosts order -- wget then tries `[::1]:8080` first
# and gets a real connection refusal (nothing is listening there), never falling back to the
# working IPv4 address. Pinning the literal IPv4 address removes the ambiguity entirely rather
# than making nginx dual-stack, which would risk `bind() to [::]:8080 failed` on a Docker
# network without IPv6 enabled (the default on Docker Desktop's bridge network).
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8080/ >/dev/null || exit 1