import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // images.remotePatterns lets Next.js <Image> load from the backend.
  // Add your tunnel hostname once you have it (see comment below).
  images: {
    remotePatterns: [
      {
        protocol: "http",
        hostname: "localhost",
        port: "8000",
      },
      // Uncomment and replace after Cloudflare Tunnel is set up:
      // {
      //   protocol: "https",
      //   hostname: "api.yourdomain.com",
      // },
    ],
  },
};

export default nextConfig;
