import { redirect } from "next/navigation";

export default function MemoryReviewRedirectPage() {
  redirect("/memory?view=curation");
}
