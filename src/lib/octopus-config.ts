/**
 * Tariff identity shared by every Next.js dashboard surface.
 *
 * Keep these public values aligned with the Railway controller's
 * OCTOPUS_PRODUCT_CODE and OCTOPUS_REGION_CODE variables.
 */
export const OCTOPUS_PRODUCT_CODE =
    process.env.NEXT_PUBLIC_OCTOPUS_PRODUCT_CODE || "AGILE-24-10-01"

export const OCTOPUS_REGION_CODE =
    process.env.NEXT_PUBLIC_OCTOPUS_REGION_CODE || "C"

export const OCTOPUS_TARIFF_CODE =
    `E-1R-${OCTOPUS_PRODUCT_CODE}-${OCTOPUS_REGION_CODE}`

export const OCTOPUS_RATES_URL =
    `https://api.octopus.energy/v1/products/${OCTOPUS_PRODUCT_CODE}/electricity-tariffs/${OCTOPUS_TARIFF_CODE}/standard-unit-rates/`
