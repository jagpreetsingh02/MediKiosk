import ConstellationField from "@/components/ui/constellation-field";

export default function ConstellationFieldDemo() {
  return (
    <div className="relative h-[640px] w-full overflow-hidden rounded-xl border border-border bg-[#070914]">
      <ConstellationField
        mode="dark"
        speed={1}
        size={1}
        strokeWidth={1}
        length={1}
        density={1}
        opacity={1}
        hue={0}
        saturation={1}
        brightness={1}
      />
    </div>
  );
}
