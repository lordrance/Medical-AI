/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";
    if (apiBase.startsWith("/")) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
      {
        source: "/healthz",
        destination: `${apiBase}/healthz`,
      },
    ];
  },
};

export default nextConfig;
