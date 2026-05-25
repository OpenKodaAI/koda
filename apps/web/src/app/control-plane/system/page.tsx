import { redirect } from "next/navigation";

export default function SystemSettingsPage() {
  redirect("/control-plane/system/general");
}
