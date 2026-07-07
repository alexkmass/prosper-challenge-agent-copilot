export function AppBrand() {
  return (
    <div className="flex shrink-0 items-center gap-1">
      <img
        src="/prosper-logo.svg"
        alt="Prosper"
        className="h-[22px] w-auto"
        draggable={false}
      />
      <h1 className="text-sm font-semibold tracking-tight">
        <span className="ml-2.5 font-medium text-muted-foreground">AI Agent Builder</span>
      </h1>
    </div>
  )
}
