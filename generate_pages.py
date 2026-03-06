"""
ENCP Services Group - SEO Landing Page Generator
3 services x 8 cities = 24 pages with UNIQUE AI-generated content per page
Uses GPT-4o-mini to generate city-specific body content, cached in content_cache.json
"""

import os
import json
import asyncio
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), 'backend', '.env'))

client = AsyncOpenAI(api_key=os.getenv('OPENAI_API_KEY'))

CACHE_FILE = 'content_cache.json'

cities = ['Boca Raton', 'Delray Beach', 'Fort Lauderdale', 'Pompano Beach', 'Coral Springs', 'Coconut Creek', 'Weston', 'Deerfield Beach']

services = {
    'Tile Installation': 'Professional tile and floor installation in {city}, FL. Porcelain, ceramic, natural stone, hardwood, laminate, and vinyl. 16+ years experience, 5-star rated.',
    'Bathroom Remodel': 'Expert bathroom remodeling in {city}, FL. Complete renovations including tile, flooring, vanities, showers, and tubs. Licensed and insured.',
    'Kitchen Remodel': 'Kitchen remodeling services in {city}, FL. Backsplash, floor tile, countertops, and complete kitchen renovations. Licensed and insured.',
}

images = {
    'Tile Installation': ('bathroom-01-luxury-final.jpeg', 'shower-03-marble-final.jpeg', 'floor-01-installation-progress.jpeg'),
    'Bathroom Remodel': ('bathroom-03-modern-final.jpeg', 'bathroom-02-luxury-angle.jpeg', 'shower-03-marble-final.jpeg'),
    'Kitchen Remodel': ('bathroom-01-luxury-final.jpeg', 'shower-02-tile-progress.jpeg', 'floor-01-installation-progress.jpeg'),
}

# ============================================
# AI Content Generation
# ============================================

CONTENT_PROMPT = """Generate UNIQUE landing page body content for a tile/flooring/remodel contractor's service page.

Company: ENCP Services Group (owners Eusebio and Tulio, 16+ years experience, 5.0 stars on Thumbtack, licensed & insured)
Service: {service}
City: {city}, FL

Write 3 sections of HTML content. Each section has an H2 and 2 paragraphs. DO NOT repeat generic company info — focus on LOCAL, SPECIFIC content.

Section 1 - "{service} Services in {city}" — Talk about:
- 2-3 REAL neighborhoods/communities/developments in {city} where this service is common
- Specific local challenges (Florida humidity, mold in bathrooms, older tile cracking, new construction needs)
- What types of properties in {city} typically need this service

Section 2 - "What {city} Homeowners Should Know About {service}" — Include:
- A specific price range typical for {city} market (be realistic for South Florida 2026)
- How long the job typically takes
- Best materials for South Florida climate (porcelain vs ceramic, waterproofing needs)
- One common mistake homeowners in this area make

Section 3 - "Trusted {service} Experts in {city}" — Cover:
- Why hiring a local South Florida contractor with tile/remodel expertise matters
- One specific Florida building code or regulation relevant to this service (waterproofing, permits)
- A real-world scenario/problem solved in the {city} area (humidity damage, old tile removal, etc.)

RULES:
- Use <h2> and <p> tags only (no <h1>, no <div>, no <section>)
- Make every sentence DIFFERENT from what you'd write for any other city
- Be specific — mention real neighborhood names, real local context
- 250-350 words total
- Professional but approachable tone (like Eusebio talking to a neighbor)
- Do NOT mention company name, phone, ratings, or insurance — those are elsewhere on the page
- Do NOT use: "In conclusion", "Look no further", "In today's world"

Return ONLY the raw HTML (h2 and p tags). No JSON wrapper, no markdown."""


async def generate_content(service: str, city: str) -> str:
    """Generate unique content for a service+city page via GPT-4o-mini"""
    prompt = CONTENT_PROMPT.format(service=service, city=city)
    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85,
        max_tokens=800,
    )
    return response.choices[0].message.content.strip()


async def generate_all_content(pages_list):
    """Generate content for all pages, using cache to skip already-generated ones"""
    cache = {}
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, 'r', encoding='utf-8') as f:
            cache = json.load(f)

    to_generate = []
    for slug, service, city, desc in pages_list:
        if slug not in cache:
            to_generate.append((slug, service, city))

    if not to_generate:
        print(f"[CACHE] All {len(pages_list)} pages already in cache.")
        return cache

    print(f"[AI] Generating unique content for {len(to_generate)} pages...")

    # Process in batches of 10
    batch_size = 10
    for i in range(0, len(to_generate), batch_size):
        batch = to_generate[i:i + batch_size]
        tasks = [generate_content(svc, city) for slug, svc, city in batch]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for j, (slug, service, city) in enumerate(batch):
            result = results[j]
            if isinstance(result, Exception):
                print(f"  [ERR] {slug}: {result}")
                cache[slug] = f'<h2>{service} Services in {city}</h2>\n<p>Professional {service.lower()} services available in {city}, FL.</p>'
            else:
                cache[slug] = result
                print(f"  [OK] {slug}")

        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)

    print(f"[AI] Done! {len(to_generate)} pages generated.")
    return cache


# ============================================
# Page list
# ============================================

pages = []
for city in cities:
    city_slug = city.lower().replace(' ', '-')
    for service, desc_tmpl in services.items():
        service_slug = service.lower().replace(' ', '-')
        slug = f'{service_slug}-{city_slug}'
        desc = desc_tmpl.format(city=city)
        pages.append((slug, service, city, desc))


# ============================================
# HTML Template
# ============================================

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
    <meta name="theme-color" content="#1B365D">
    <title>{service} in {city}, FL | ENCP Services Group</title>
    <meta name="description" content="{desc}">
    <link rel="canonical" href="https://encpservices.com/{slug}/">
    <meta name="geo.region" content="US-FL">
    <meta name="geo.placename" content="{city}">
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://encpservices.com/{slug}/">
    <meta property="og:title" content="{service} in {city}, FL | ENCP Services Group">
    <meta property="og:description" content="{desc}">
    <meta property="og:image" content="https://encpservices.com/assets/fotos/bathroom-01-luxury-final.jpeg">
    <meta property="og:locale" content="en_US">
    <link rel="icon" type="image/png" href="/assets/logo/favicon-32.png">
    <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&family=Open+Sans:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/styles.css">
    <script type="application/ld+json">
    {{
        "@context": "https://schema.org",
        "@type": "Service",
        "name": "{service} in {city}, FL",
        "description": "{desc}",
        "provider": {{
            "@type": "HomeAndConstructionBusiness",
            "name": "ENCP Services Group",
            "telephone": "+1-561-506-7035",
            "url": "https://encpservices.com",
            "address": {{
                "@type": "PostalAddress",
                "addressLocality": "{city}",
                "addressRegion": "FL",
                "addressCountry": "US"
            }},
            "aggregateRating": {{
                "@type": "AggregateRating",
                "ratingValue": "5.0",
                "reviewCount": "20"
            }}
        }},
        "areaServed": {{
            "@type": "City",
            "name": "{city}, FL"
        }}
    }}
    </script>
    <style>
        .service-hero {{
            background: linear-gradient(135deg, #1B365D 0%, #2a4a7a 100%);
            color: white;
            padding: 120px 20px 60px;
            text-align: center;
        }}
        .service-hero h1 {{
            font-family: 'Montserrat', sans-serif;
            font-size: 2.5rem;
            margin-bottom: 15px;
        }}
        .service-hero p {{
            font-size: 1.15rem;
            opacity: 0.9;
            max-width: 700px;
            margin: 0 auto 30px;
            line-height: 1.6;
        }}
        .service-content {{
            max-width: 900px;
            margin: 0 auto;
            padding: 60px 20px;
        }}
        .service-content h2 {{
            font-family: 'Montserrat', sans-serif;
            color: #1B365D;
            font-size: 1.8rem;
            margin-bottom: 20px;
        }}
        .service-content p {{
            line-height: 1.8;
            color: #444;
            margin-bottom: 20px;
            font-size: 1.05rem;
        }}
        .service-gallery {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin: 40px 0;
        }}
        .service-gallery img {{
            width: 100%;
            border-radius: 10px;
            object-fit: cover;
            height: 250px;
        }}
        .lp-benefits {{
            background: #f8f9fa;
            padding: 50px 20px;
        }}
        .lp-benefits h2 {{
            text-align: center;
            font-family: 'Montserrat', sans-serif;
            color: #1B365D;
            margin-bottom: 40px;
            font-size: 1.8rem;
        }}
        .lp-benefits-grid {{
            max-width: 900px;
            margin: 0 auto;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 30px;
        }}
        .lp-benefit {{ text-align: center; padding: 20px; }}
        .lp-benefit h3 {{
            font-family: 'Montserrat', sans-serif;
            color: #1B365D;
            margin-bottom: 10px;
        }}
        .lp-benefit p {{ color: #666; line-height: 1.6; }}
        .service-cta {{
            background: #1B365D;
            color: white;
            text-align: center;
            padding: 60px 20px;
        }}
        .service-cta h2 {{
            font-family: 'Montserrat', sans-serif;
            margin-bottom: 15px;
            font-size: 1.8rem;
        }}
        .service-cta p {{ margin-bottom: 25px; opacity: 0.9; font-size: 1.1rem; }}
        @media (max-width: 768px) {{
            .service-hero {{ padding: 100px 20px 40px; }}
            .service-hero h1 {{ font-size: 1.8rem; }}
            .service-hero p {{ font-size: 1rem; }}
        }}
    </style>
</head>
<body>
    <!-- HEADER (same as main site) -->
    <header class="header">
        <div class="container header-content">
            <a href="/" class="logo">
                <img src="/assets/logo/encp-logo-horizontal.png" alt="ENCP Services Group" width="900" height="240">
            </a>
            <nav class="nav">
                <a href="/">Home</a>
                <a href="/#services">Services</a>
                <a href="/#portfolio">Portfolio</a>
                <a href="/#reviews">Reviews</a>
                <a href="/#contact">Contact</a>
            </nav>
            <a href="tel:+15615067035" class="btn btn-primary header-cta">Call (561) 506-7035</a>
            <button class="mobile-menu-btn" aria-label="Menu">
                <span></span>
                <span></span>
                <span></span>
            </button>
        </div>
    </header>

    <section class="service-hero">
        <h1>{service} in {city}, FL</h1>
        <p>{desc}</p>
        <a href="tel:+15615067035" class="btn btn-gold btn-large">Call For Free Estimate</a>
    </section>

    <!-- CONTENT (AI-generated unique per city+service) -->
    <section class="service-content">
        {body_content}

        <div class="service-gallery">
            <img src="/assets/fotos/{img1}" alt="{service} project in {city} FL by ENCP Services" width="400" height="250" loading="lazy">
            <img src="/assets/fotos/{img2}" alt="Professional {service_lower} {city} Florida" width="400" height="250" loading="lazy">
            <img src="/assets/fotos/{img3}" alt="{service} work in progress {city} FL" width="400" height="250" loading="lazy">
        </div>
    </section>

    <section class="lp-benefits">
        <h2>Why ENCP Services Group?</h2>
        <div class="lp-benefits-grid">
            <div class="lp-benefit">
                <h3>16+ Years Experience</h3>
                <p>Over a decade and a half of professional tile and flooring expertise in South Florida.</p>
            </div>
            <div class="lp-benefit">
                <h3>5.0 Star Rating</h3>
                <p>100% five-star reviews from satisfied homeowners across {city} and South Florida.</p>
            </div>
            <div class="lp-benefit">
                <h3>Free Estimates</h3>
                <p>Detailed, no-obligation estimates for every project. No surprises, no hidden fees.</p>
            </div>
            <div class="lp-benefit">
                <h3>Licensed & Insured</h3>
                <p>Fully licensed and insured for your complete peace of mind on every job.</p>
            </div>
        </div>
    </section>

    <section class="service-cta">
        <h2>Ready to Start Your {service} Project?</h2>
        <p>Contact us today for a free estimate in {city}, FL. We'll visit your property, discuss your vision, and provide a detailed quote.</p>
        <a href="tel:+15615067035" class="btn btn-gold btn-large">Call (561) 506-7035</a>
    </section>

    <!-- FOOTER (same as main site) -->
    <footer class="footer">
        <div class="container">
            <div class="footer-content">
                <div class="footer-brand">
                    <img src="/assets/logo/encp-logo-white.png" alt="ENCP Services Group" class="footer-logo" width="1200" height="360">
                    <p>Excellence in Every Detail</p>
                </div>
                <div class="footer-links">
                    <h4>Quick Links</h4>
                    <a href="/">Home</a>
                    <a href="/#services">Services</a>
                    <a href="/#portfolio">Portfolio</a>
                    <a href="/#reviews">Reviews</a>
                    <a href="/#contact">Contact</a>
                </div>
                <div class="footer-services">
                    <h4>Services</h4>
                    <a href="/tile-installation-boca-raton/">Tile Installation</a>
                    <a href="/bathroom-remodel-boca-raton/">Bathroom Remodel</a>
                    <a href="/kitchen-remodel-boca-raton/">Kitchen Remodel</a>
                </div>
                <div class="footer-contact">
                    <h4>Contact</h4>
                    <span>{city}, FL</span>
                    <a href="tel:+15615067035">(561) 506-7035</a>
                    <a href="mailto:encpservicesgroup@gmail.com">encpservicesgroup@gmail.com</a>
                </div>
            </div>
            <div class="thumbtack-badge">
                <a href="https://www.thumbtack.com/fl/boca-raton/tile/encp-services-group/service/335989598897750230" target="_blank" rel="noopener" class="thumbtack-link">
                    <div class="thumbtack-rating">
                        <span class="thumbtack-exceptional">Exceptional 5.0</span>
                        <span class="thumbtack-stars">&#9733;&#9733;&#9733;&#9733;&#9733;</span>
                        <span class="thumbtack-reviews">(20)</span>
                    </div>
                    <span class="thumbtack-divider"></span>
                    <img src="/assets/thumbtack-logo.svg" alt="Thumbtack" class="thumbtack-logo" width="120" height="24">
                </a>
            </div>
            <div class="footer-bottom">
                <p>&copy; 2026 ENCP Services Group. All rights reserved.</p>
            </div>
        </div>
    </footer>

    <script>
        document.querySelector('.mobile-menu-btn').addEventListener('click', function() {{
            document.querySelector('.nav').classList.toggle('active');
            this.classList.toggle('active');
        }});
        window.addEventListener('scroll', function() {{
            const header = document.querySelector('.header');
            if (window.scrollY > 50) {{
                header.classList.add('scrolled');
            }} else {{
                header.classList.remove('scrolled');
            }}
        }});
    </script>
</body>
</html>"""


# ============================================
# Build pages
# ============================================

async def main():
    content_cache = await generate_all_content(pages)

    for slug, service, city, desc in pages:
        dir_path = f'c:/enpcservices/public/{slug}'
        os.makedirs(dir_path, exist_ok=True)

        imgs = images.get(service, images['Tile Installation'])
        body_content = content_cache.get(slug, f'<h2>{service} in {city}</h2><p>Professional services available.</p>')

        html = TEMPLATE.format(
            service=service,
            city=city,
            desc=desc,
            slug=slug,
            service_lower=service.lower(),
            img1=imgs[0],
            img2=imgs[1],
            img3=imgs[2],
            body_content=body_content,
        )

        with open(f'{dir_path}/index.html', 'w', encoding='utf-8') as f:
            f.write(html)

    print(f'\n[DONE] {len(pages)} pages created with unique AI content')


if __name__ == '__main__':
    asyncio.run(main())
