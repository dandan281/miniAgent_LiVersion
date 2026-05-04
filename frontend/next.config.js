/** @type {import('next').NextConfig} */
const nextConfig = {
  distDir: process.env.NEXT_DIST_DIR || ".next",
  async rewrites() {
    const apiBase =
      process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
      `http://127.0.0.1:${process.env.NEXT_PUBLIC_API_PORT || "8002"}`;

    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
      {
        source: "/backend-health",
        destination: `${apiBase}/`,
      },
    ];
  },
};

module.exports = nextConfig;
