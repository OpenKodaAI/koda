import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "./select";

describe("Select", () => {
  it("renders a searchable input inside generic select content", async () => {
    render(
      <Select defaultValue="default">
        <SelectTrigger>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="default">Select a default model</SelectItem>
          <SelectGroup>
            <SelectLabel>OpenAI</SelectLabel>
            <SelectItem value="gpt">GPT-4o mini Transcribe</SelectItem>
            <SelectItem value="whisper">Whisper API</SelectItem>
          </SelectGroup>
          <SelectGroup>
            <SelectLabel>ElevenLabs</SelectLabel>
            <SelectItem value="scribe">Scribe v1</SelectItem>
          </SelectGroup>
        </SelectContent>
      </Select>,
    );

    fireEvent.click(screen.getByRole("combobox"));

    const search = screen.getByRole("textbox", { name: "Search options" });
    expect(search).toBeInTheDocument();
    expect(screen.getByText("GPT-4o mini Transcribe")).toBeVisible();

    fireEvent.change(search, { target: { value: "v1" } });

    expect(screen.getByText("Scribe v1")).toBeVisible();
    await waitFor(() => {
      expect(
        screen.getByText("GPT-4o mini Transcribe").closest("[data-slot='select-item']"),
      ).not.toBeVisible();
    });
  });
});
