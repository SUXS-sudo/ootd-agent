import Image, { ImageProps } from "next/image";

type AppImageProps = Omit<ImageProps, "width" | "height" | "unoptimized"> & {
  width?: number;
  height?: number;
};

export function AppImage({ src, alt, width = 640, height = 800, sizes, ...props }: AppImageProps) {
  return (
    <Image
      {...props}
      src={src}
      alt={alt}
      width={width}
      height={height}
      sizes={sizes ?? "(max-width: 768px) 50vw, 320px"}
      // Wardrobe images are already final local/API assets. Vinext's local
      // Cloudflare runtime does not always expose an ASSETS Fetcher, so routing
      // relative sources through /_vinext/image can crash the whole page.
      unoptimized
    />
  );
}
