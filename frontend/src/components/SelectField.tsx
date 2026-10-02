import * as Select from "@radix-ui/react-select";
import { Check, ChevronDown } from "lucide-react";

type SelectOption = { value: string; label: string };

export function SelectField({ label, value, options, onValueChange }: { label: string; value: string; options: SelectOption[]; onValueChange: (value: string) => void }) {
  return <Select.Root value={value} onValueChange={onValueChange}><Select.Trigger className="select-trigger" aria-label={label}><Select.Value /><Select.Icon><ChevronDown size={15} /></Select.Icon></Select.Trigger><Select.Portal><Select.Content className="select-content" position="popper" sideOffset={5}><Select.Viewport className="select-viewport">{options.map((option) => <Select.Item className="select-item" key={option.value} value={option.value}><Select.ItemIndicator><Check size={14} /></Select.ItemIndicator><Select.ItemText>{option.label}</Select.ItemText></Select.Item>)}</Select.Viewport></Select.Content></Select.Portal></Select.Root>;
}
