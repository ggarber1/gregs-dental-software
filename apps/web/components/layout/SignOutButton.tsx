"use client";

import { useRouter } from "next/navigation";

import { clearSession } from "@/lib/auth/clientSession";

export function SignOutButton() {
  const router = useRouter();

  async function handleSignOut() {
    await clearSession();
    router.push("/login");
  }

  return (
    <button
      type="button"
      className="w-full text-left"
      onClick={() => void handleSignOut()}
    >
      Sign out
    </button>
  );
}
