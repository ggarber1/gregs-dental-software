import { redirect } from "next/navigation";

export default function InsuranceARPage() {
  redirect("/billing/claims?tab=awaiting");
}
