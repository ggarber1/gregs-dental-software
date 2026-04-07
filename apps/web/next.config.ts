import path from "path";
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Transpile monorepo packages so Next.js can process their TypeScript/ESM
  transpilePackages: ["@dental/ui", "@dental/shared-types"],
  // Required for Docker standalone deployment
  output: "standalone",
  // Tells Next.js to trace dependencies from the monorepo root so it follows
  // pnpm symlinks into the .pnpm virtual store and copies real files.
  // Without this, standalone node_modules contain empty symlink targets.
  outputFileTracingRoot: path.join(__dirname, "../../"),
};

export default nextConfig;
