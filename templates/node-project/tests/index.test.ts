import { greet } from "../src/{{NODE_PACKAGE}}/index.js";

describe("greet", () => {
  it("greets by name", () => {
    expect(greet("world")).toBe("Hello, world!");
  });
});
