import { headers } from "next/headers";
import { RootRouteLoadingForPathname } from "@/components/layout/root-route-loading";

export default async function Loading() {
  const headerStore = await headers();
  return (
    <RootRouteLoadingForPathname
      pathname={headerStore.get("x-koda-pathname")}
    />
  );
}
