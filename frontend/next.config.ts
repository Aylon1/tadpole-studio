import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  devIndicators: false,
  allowedOrigins: [
    "http://localhost:3000",
    "http://localhost:8700",
    "http://8700",
    "http://127.0.0.1:3000",
  ],
};

export default nextConfig;
