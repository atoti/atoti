# Build from source

Extract the contents from within `source.zip` and move the `packages` folder to `source`. Then, execute the following commands within `source`:

> **Note:** Set your [Artifactory credentials](https://docs.activeviam.com/products/atoti/ui/latest/docs/tutorial/setup/).

```sh
yarn install
yarn build
```

Make sure to replace `./packages` with the new build `./source/packages`.