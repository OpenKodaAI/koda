import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { InsecureTransportScreen } from "@/components/auth/insecure-transport-screen";
import { I18nProvider } from "@/components/providers/i18n-provider";

describe("InsecureTransportScreen", () => {
  it("names the plain-HTTP address and the two ways to reach the dashboard (J-14)", () => {
    render(
      <I18nProvider initialLanguage="en-US">
        <InsecureTransportScreen origin="http://192.168.1.10:3000" />
      </I18nProvider>,
    );

    expect(screen.getByRole("heading", { level: 1, name: /https required/i })).toBeInTheDocument();
    expect(screen.getByText(/http:\/\/192\.168\.1\.10:3000/)).toBeInTheDocument();
    expect(screen.getByText(/reverse proxy/i)).toBeInTheDocument();
    expect(screen.getByText(/localhost/i)).toBeInTheDocument();
    // Nothing to submit: a session started here would be dropped by the browser.
    expect(screen.queryByLabelText(/password/i)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /sign in|create account/i })).not.toBeInTheDocument();
  });
});
