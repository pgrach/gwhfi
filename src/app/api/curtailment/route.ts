import { NextResponse } from "next/server";

const CURTAILCOIN_BASE = "https://curtailcoin.com/api";

interface CurtailCoinSummary {
    totalCurtailedEnergy: number; // MWh
    totalPayment: number;
    totalPotentialBtc: number;
    difficulty: number;
}

interface CurtailCoinMonthly {
    totalCurtailedEnergy: number; // MWh
    totalPayment: number;
}

function todayDateString(): string {
    const now = new Date();
    return now.toISOString().slice(0, 10);
}

async function fetchBtcPriceGbp(): Promise<number | null> {
    // Try CoinGecko first
    try {
        const res = await fetch(
            "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=gbp",
            { signal: AbortSignal.timeout(5000) }
        );
        if (res.ok) {
            const data = await res.json();
            if (data?.bitcoin?.gbp) return data.bitcoin.gbp;
        }
    } catch {
        // CoinGecko failed, try CoinCap as fallback
    }

    // Fallback: CoinCap (returns USD) + approximate GBP conversion
    try {
        const res = await fetch("https://api.coincap.io/v2/assets/bitcoin", {
            signal: AbortSignal.timeout(5000),
        });
        if (res.ok) {
            const data = await res.json();
            const usdPrice = parseFloat(data?.data?.priceUsd);
            if (usdPrice) return Math.round(usdPrice * 0.79); // Approximate USD→GBP
        }
    } catch {
        // Both APIs failed
    }

    return null;
}

export async function GET() {
    const dateStr = todayDateString();

    try {
        const [dailyRes, monthlyRes, btcPriceGbp] = await Promise.all([
            fetch(`${CURTAILCOIN_BASE}/summary/${dateStr}`, {
                next: { revalidate: 3600 },
            }),
            fetch(`${CURTAILCOIN_BASE}/summary/monthly/${dateStr}`, {
                next: { revalidate: 3600 },
            }),
            fetchBtcPriceGbp(),
        ]);

        if (!dailyRes.ok || !monthlyRes.ok) {
            return NextResponse.json(
                { error: "CurtailCoin API unavailable" },
                { status: 502 }
            );
        }

        const daily: CurtailCoinSummary = await dailyRes.json();
        const monthly: CurtailCoinMonthly = await monthlyRes.json();

        const btcMined = daily.totalPotentialBtc;
        const btcValueGbp =
            btcPriceGbp && btcMined ? +(btcMined * btcPriceGbp).toFixed(0) : null;

        return NextResponse.json({
            today: {
                energy_gwh: +(daily.totalCurtailedEnergy / 1000).toFixed(2),
                energy_mwh: +daily.totalCurtailedEnergy.toFixed(1),
                payment: +daily.totalPayment.toFixed(0),
                btc: +btcMined.toFixed(2),
                btc_value_gbp: btcValueGbp,
            },
            month: {
                energy_gwh: +(monthly.totalCurtailedEnergy / 1000).toFixed(1),
                energy_mwh: +monthly.totalCurtailedEnergy.toFixed(0),
                payment: +monthly.totalPayment.toFixed(0),
            },
            btc_price_gbp: btcPriceGbp,
            date: dateStr,
            source: "https://curtailcoin.com",
        });
    } catch {
        return NextResponse.json(
            { error: "Failed to fetch curtailment data" },
            { status: 502 }
        );
    }
}
