import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Do not let a package-lock.json higher in the directory tree become the
  // inferred workspace root on developer machines.
  turbopack: {
    root: process.cwd(),
  },
};

export default nextConfig;
