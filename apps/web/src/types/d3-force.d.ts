declare module "d3-force" {
  export interface SimulationNodeDatum {
    index?: number;
    x?: number;
    y?: number;
    vx?: number;
    vy?: number;
    fx?: number | null;
    fy?: number | null;
  }

  export interface SimulationLinkDatum<NodeDatum extends SimulationNodeDatum> {
    source: NodeDatum | string | number;
    target: NodeDatum | string | number;
    index?: number;
  }

  export interface Force<NodeDatum extends SimulationNodeDatum> {
    (alpha: number): void;
    initialize?: (nodes: NodeDatum[], random: () => number) => void;
  }

  export interface Simulation<NodeDatum extends SimulationNodeDatum> {
    nodes(): NodeDatum[];
    nodes(nodes: NodeDatum[]): this;
    force(name: string): unknown;
    force<F>(name: string, force: F | null): this;
    alpha(): number;
    alpha(alpha: number): this;
    alphaMin(): number;
    alphaMin(min: number): this;
    alphaDecay(): number;
    alphaDecay(decay: number): this;
    alphaTarget(): number;
    alphaTarget(target: number): this;
    velocityDecay(): number;
    velocityDecay(decay: number): this;
    restart(): this;
    stop(): this;
    tick(iterations?: number): this;
    on(type: string, listener: ((this: this) => void) | null): this;
    find(x: number, y: number, radius?: number): NodeDatum | undefined;
  }

  export function forceSimulation<NodeDatum extends SimulationNodeDatum>(
    nodes?: NodeDatum[],
  ): Simulation<NodeDatum>;

  export interface ForceLink<
    NodeDatum extends SimulationNodeDatum,
    LinkDatum extends SimulationLinkDatum<NodeDatum>,
  > extends Force<NodeDatum> {
    links(): LinkDatum[];
    links(links: LinkDatum[]): this;
    id(accessor: (node: NodeDatum) => string | number): this;
    distance(value: number | ((link: LinkDatum) => number)): this;
    strength(value: number | ((link: LinkDatum) => number)): this;
    iterations(count: number): this;
  }

  export function forceLink<
    NodeDatum extends SimulationNodeDatum,
    LinkDatum extends SimulationLinkDatum<NodeDatum>,
  >(links?: LinkDatum[]): ForceLink<NodeDatum, LinkDatum>;

  export interface ForceManyBody<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum> {
    strength(value: number | ((node: NodeDatum) => number)): this;
    theta(value: number): this;
    distanceMin(value: number): this;
    distanceMax(value: number): this;
  }

  export function forceManyBody<NodeDatum extends SimulationNodeDatum>(): ForceManyBody<NodeDatum>;

  export interface ForceCollide<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum> {
    radius(value: number | ((node: NodeDatum) => number)): this;
    strength(value: number): this;
    iterations(count: number): this;
  }

  export function forceCollide<NodeDatum extends SimulationNodeDatum>(): ForceCollide<NodeDatum>;

  export interface ForceCenter<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum> {
    x(value: number): this;
    y(value: number): this;
    strength(value: number): this;
  }

  export function forceCenter<NodeDatum extends SimulationNodeDatum>(
    x?: number,
    y?: number,
  ): ForceCenter<NodeDatum>;

  export interface ForceXY<NodeDatum extends SimulationNodeDatum> extends Force<NodeDatum> {
    strength(value: number | ((node: NodeDatum) => number)): this;
    x(value: number | ((node: NodeDatum) => number)): this;
    y(value: number | ((node: NodeDatum) => number)): this;
  }

  export function forceX<NodeDatum extends SimulationNodeDatum>(
    x?: number | ((node: NodeDatum) => number),
  ): ForceXY<NodeDatum>;

  export function forceY<NodeDatum extends SimulationNodeDatum>(
    y?: number | ((node: NodeDatum) => number),
  ): ForceXY<NodeDatum>;
}
