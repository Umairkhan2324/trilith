import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/trilith/:path*",
        destination: `${process.env.TRILITH_API_URL ?? "http://127.0.0.1:8080"}/:path*`,
      },
    ];
  },
};

export default nextConfig;
