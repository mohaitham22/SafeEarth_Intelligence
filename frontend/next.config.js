// Next.js 14 + next-pwa configuration.
//
// PWA caching rules (CLAUDE.md binding — no exceptions):
//   CACHE ONLY:  /recommendations, /regions/trends, /regions/continent-stats,
//                /regions/seasonal-peaks, /regions/secondary-disasters
//   NEVER CACHE: POST routes, /api/auth/*, authenticated user data
//
// Windows dev fix: disable: process.env.NODE_ENV !== 'production'
//   next-pwa generates sw.js in dev mode which causes permission errors on
//   Windows (can't overwrite the file on hot-reload) and slows HMR.
//   Service worker is active ONLY in production builds.

const withPWA = require('next-pwa')({
  dest: 'public',
  disable: process.env.NODE_ENV !== 'production',
  // Opt out of next-pwa's default precache of all Next.js static chunks —
  // we manage caching entirely via the explicit runtimeCaching list below.
  skipWaiting: true,
  clientsClaim: true,
  runtimeCaching: [
    {
      urlPattern: /\/api\/v1\/recommendations(\?.*)?$/,
      handler: 'NetworkFirst',
      options: {
        cacheName: 'safeearth-recommendations',
        expiration: { maxEntries: 10, maxAgeSeconds: 86400 },
      },
    },
    {
      urlPattern: /\/api\/v1\/regions\/trends(\?.*)?$/,
      handler: 'NetworkFirst',
      options: {
        cacheName: 'safeearth-regions-trends',
        expiration: { maxEntries: 5, maxAgeSeconds: 86400 },
      },
    },
    {
      urlPattern: /\/api\/v1\/regions\/continent-stats(\?.*)?$/,
      handler: 'NetworkFirst',
      options: {
        cacheName: 'safeearth-regions-continent-stats',
        expiration: { maxEntries: 5, maxAgeSeconds: 86400 },
      },
    },
    {
      urlPattern: /\/api\/v1\/regions\/seasonal-peaks(\?.*)?$/,
      handler: 'NetworkFirst',
      options: {
        cacheName: 'safeearth-regions-seasonal-peaks',
        expiration: { maxEntries: 5, maxAgeSeconds: 86400 },
      },
    },
    {
      urlPattern: /\/api\/v1\/regions\/secondary-disasters(\?.*)?$/,
      handler: 'NetworkFirst',
      options: {
        cacheName: 'safeearth-regions-secondary-disasters',
        expiration: { maxEntries: 5, maxAgeSeconds: 86400 },
      },
    },
  ],
})

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Silence punycode deprecation warning from Node 18+ (comes from transitive deps)
  experimental: {},
}

module.exports = withPWA(nextConfig)
