"use client";

import { useRouter } from "next/navigation";
import { signOut } from "aws-amplify/auth";

export function SignOutButton() {
  const router = useRouter();

  async function handleSignOut() {
    try {
      await signOut();
    } catch {
      // Amplify sign-out failures are non-fatal — proceed to clear cookies.
    }
    await fetch("/_session", { method: "DELETE" });
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
