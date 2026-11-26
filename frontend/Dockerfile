# FinSight Frontend - Multi-stage Dockerfile
# Target: development (default), production

# -----------------------------------------------------------------------------
# Base stage - common dependencies
# -----------------------------------------------------------------------------
FROM node:20-alpine AS base

ENV NODE_ENV=development \
    NEXT_TELEMETRY_DISABLED=1

# Install system dependencies
RUN apk add --no-cache \
    libc6-compat \
    curl

# Align non-root user UID/GID with 1000 so dev bind-mounts stay writable
RUN deluser --remove-home node && \
    addgroup -g 1000 -S finsight && \
    adduser -S finsight -u 1000 -G finsight

WORKDIR /app

# -----------------------------------------------------------------------------
# Development stage - with hot reload
# -----------------------------------------------------------------------------
FROM base AS development

# Prepare writable directories and run npm ci as non-root user
RUN mkdir -p /app/node_modules /app/.next && chown -R finsight:finsight /app

USER finsight

# Copy package files and install all dependencies (including dev)
COPY --chown=finsight:finsight package*.json ./
RUN npm ci

# Copy source code
COPY --chown=finsight:finsight . .

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:3000 || exit 1

# Default command with hot reload
CMD ["npm", "run", "dev"]

# -----------------------------------------------------------------------------
# Builder stage - production build
# -----------------------------------------------------------------------------
FROM base AS builder

# Copy package files and install all deps needed for build (typescript, tailwindcss, etc.)
COPY package*.json ./
RUN npm ci --include=dev

# Copy source code
COPY --chown=finsight:finsight . .

# Build application in production mode
ENV NODE_ENV=production
RUN npm run build

# -----------------------------------------------------------------------------
# Production stage - optimized, standalone output
# -----------------------------------------------------------------------------
FROM base AS production

ENV NODE_ENV=production \
    HOSTNAME="0.0.0.0" \
    PORT=3000

# Copy standalone build output
COPY --from=builder --chown=finsight:finsight /app/public ./public
COPY --from=builder --chown=finsight:finsight /app/.next/standalone ./
COPY --from=builder --chown=finsight:finsight /app/.next/static ./.next/static

# Switch to non-root user
USER finsight

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:3000 || exit 1

# Production command
CMD ["node", "server.js"]
