"use client";

import { useEffect } from "react";
import { configureBackendUrl } from "@/lib/backend-url";

export default function BackendConfig({ backendUrl }: { backendUrl: string }) {
  useEffect(() => {
    if (backendUrl) configureBackendUrl(backendUrl);
  }, [backendUrl]);

  if (backendUrl) configureBackendUrl(backendUrl);
  return null;
}
