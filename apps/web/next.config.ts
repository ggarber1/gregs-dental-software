import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Transpile monorepo packages so Next.js can process their TypeScript/ESM
  transpilePackages: ["@dental/ui", "@dental/shared-types"],
};

export default nextConfig;
