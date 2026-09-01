/** @type {import('next').NextConfig} */
const nextConfig = {
  async rewrites() {
    const api = process.env.BACKEND_URL || "http://localhost:8000";
    return [
      { source: "/api/:path*", destination: `${api}/:path*` },
      { source: "/clips/:path*", destination: `${api}/clips/:path*` },
    ];
  },
};

export default nextConfig;
