import streamlit as st
from exa_py import Exa  # For web search functionality
import httpx  # For making HTTP requests
import os  # For interacting with the operating system
import json  # For JSON data handling
from datetime import datetime, timedelta, timezone  # For working with dates and times
from utils import initialize_exa  # Import the initialize_exa function
from dotenv import load_dotenv  # For loading environment variables

# Load environment variables from .env file
load_dotenv()

# Constants
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    st.error("OPENROUTER_API_KEY not found in environment variables.")
    st.stop()

API_BASE_URL = "https://openrouter.ai/api/v1"
HEADERS = {"Authorization": f"Bearer {OPENROUTER_API_KEY}"}

# Initialize HTTP client
client = httpx.Client(base_url=API_BASE_URL, headers=HEADERS)

# Function to perform web research using Exa API
def perform_web_research(exa_client, query, num_results=5, hours_back=24, selected_categories=None):
    try:
        # Get current time in UTC
        now = datetime.now(timezone.utc)
        
        # Calculate start date based on hours_back
        start_date = now - timedelta(hours=hours_back)
        
        # Format dates in ISO format for Exa API
        start_date_str = start_date.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        end_date_str = now.strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z'
        
        print(f"Debug - Search parameters:")
        print(f"Query: {query}")
        print(f"Start date: {start_date_str}")
        print(f"End date: {end_date_str}")
        print(f"Categories to search: {selected_categories}")
        print(f"Results per category: {num_results}")
        
        all_categories = ["company", "research_paper", "news", "tweet", 
                         "personal_site", "pdf"]
        
        categories_to_search = (all_categories if "all" in selected_categories 
                              else selected_categories or all_categories)
        
        all_results = []
        successful_categories = []
        failed_categories = []
        
        for category in categories_to_search:
            try:
                # Use search_and_contents with date parameters
                result = exa_client.search_and_contents(
                    query,
                    type="neural",
                    num_results=num_results,
                    category=category,
                    text=True,
                    use_autoprompt=True,
                    start_published_date=start_date_str,
                    end_published_date=end_date_str
                )
                
                if result and result.results:
                    all_results.extend(result.results)
                    successful_categories.append(category)
                    print(f"Success - Category {category}: Found {len(result.results)} results")
                else:
                    failed_categories.append(category)
                    print(f"No results found for category {category}")
                    
            except Exception as e:
                failed_categories.append(category)
                print(f"Error in category {category}: {str(e)}")
                continue
        
        # Provide feedback about the search results
        if successful_categories:
            st.info(f"Found results in categories: {', '.join(successful_categories)}")
        if failed_categories:
            st.warning(f"No results found in categories: {', '.join(failed_categories)}")
        
        if not all_results:
            print("Debug - No results found in any category")
            suggestions = [
                "Try a broader search query",
                "Increase the time window",
                "Select different categories",
                "Check if the query contains any special characters",
                "Try using more general keywords"
            ]
            st.error("No results found. Suggestions:")
            for suggestion in suggestions:
                st.write(f"• {suggestion}")
            return None
        
        # Sort results by score
        all_results.sort(key=lambda x: x.score if x.score is not None else 0, reverse=True)
        print(f"Debug - Total results found: {len(all_results)}")
        return type('SearchResponse', (), {'results': all_results})
    
    except Exception as e:
        print(f"Debug - Main error: {str(e)}")
        st.error(f"Error during research: {str(e)}")
        return None

# Function to serialize search results
def serialize_search_results(search_result):
    serialized_results = {
        "results": [
            {
                "title": result.title,
                "url": result.url,
                "published_date": result.published_date,  # This is the raw date from Exa
                "author": result.author,
                "score": result.score,
                "text": result.text,
                "highlights": result.highlights,
                "highlight_scores": result.highlight_scores,
            }
            for result in search_result.results
        ]
    }
    
    # Debug print to see actual dates
    for result in serialized_results["results"]:
        print(f"Raw published date for {result['title'][:30]}...: {result['published_date']}")
    
    return serialized_results

# Add this new function to escape markdown characters
def escape_markdown_characters(text):
    # Escape characters that trigger markdown formatting
    markdown_chars = ['_', '*']
    for char in markdown_chars:
        text = text.replace(char, '\\' + char)
    return text

# Update the prepare_content_for_gpt function
def prepare_content_for_gpt(serialized_results, selected_indices):
    content = "Create a markdown article about the researched topic, using the relevant URLs as citations where necessary:\n\n"
    for i, item in enumerate(serialized_results["results"], 1):
        if i in selected_indices:
            # Escape markdown characters in title and text
            safe_title = escape_markdown_characters(item['title'])
            safe_text = escape_markdown_characters(item['text'])
            content += f"Title: {safe_title}\nURL: {item['url']}\nText: {safe_text}\n\n"
    return content

# Function to generate article using OpenRouter's API
def generate_article(content, query):
    payload = {
        "model": "anthropic/claude-3.5-sonnet",
        "messages": [
            {
                "role": "system",
                "content": f"""
You are an expert Thai technology journalist with extensive knowledge across various aspects of '{query}' topic. 
Your task is to create a detailed, well-researched, and insightful article about {query}. The article should be tailored for a Thai audience interested in {query}.

Please structure your Thai-language article with the following elements:

**STRICT FORMAT REQUIREMENTS:**
1. **First lines must be exactly:**
   - **Title:** [60 characters max]
   - **Meta Description:** [160 characters max]
   - **Excerpt:** [2 sentences max, for social sharing]
   - **# [Title repeated]**

2. **Structure:**
   - Introduction paragraph: Introduce the topic and its significance in the tech world.
   - Use 2-3 section headings (##).
   - For each heading, provide 2-3 paragraphs of interesting explanations.
   - Do not use repetitive sentences.
   - Ensure each paragraph serves a unique purpose.

3. **Guidelines:**
   - Write in Thai, making complex concepts accessible.
   - Keep entity and technical terms in English (e.g., people names, organisation names, platforms, technical concepts, product names).
   - Use English names for cryptocurrencies (e.g., use 'Bitcoin' not 'บิทคอยน์').
   - Include relevant sources as in-text citations formatted as (อ้างอิง: Brand Name) with clickable hyperlinks.
   - Ensure smooth transitions between sections.

4. **Required Additional Sections:**
   - Conclusion (without heading): Summarize key points and implications
   - **Image Prompt:** [One short sentence describing the main visual concept, max 20 words]

5. **Content Guidelines:**
   - Use clear and engaging Thai language
   - Avoid unnecessary technical jargon
   - Focus on value-adding information
   - Maintain professional tone while being accessible

Use the provided research content to create an informative and engaging article following these guidelines.
"""
            },
            {
                "role": "user",
                "content": content
            }
        ],
        "temperature": 0.7,
        "max_tokens": 4000
    }

    try:
        response = client.post("/chat/completions", json=payload)
        response.raise_for_status()
        data = response.json()
        
        # Extract the generated article content
        article_content = data['choices'][0]['message']['content']
        title, meta_description = extract_metadata(article_content)
        
        if not title or not meta_description:
            # Generate missing metadata in Thai
            metadata_prompt = f"Based on this Thai article content, generate a:\n1. Title in Thai (60 chars max)\n2. Meta description in Thai (160 chars max)\n\nArticle:\n{article_content}"
            metadata_response = client.post("/chat/completions", json={
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [
                    {"role": "system", "content": "You are a Thai SEO expert. Return only the Title and Meta Description in Thai, each on a new line, prefixed with 'Title: ' and 'Meta Description: '."},
                    {"role": "user", "content": metadata_prompt}
                ],
                "temperature": 0.7
            })
            
            metadata = metadata_response.json()['choices'][0]['message']['content']
            new_title, new_meta = extract_metadata(metadata)
            
            # Insert the generated metadata at the start of the article
            if not title:
                title = new_title
            if not meta_description:
                meta_description = new_meta
                
            article_content = f"Title: {title}\nMeta Description: {meta_description}\n# {title}\n\n{article_content}"
            
        return article_content, title, meta_description
    except httpx.HTTPStatusError as exc:
        st.error(f"HTTP error occurred: {exc.response.status_code} - {exc.response.text}")
    except Exception as e:
        st.error(f"An error occurred: {e}")
    return None, None, None

# Function to extract Title and Meta Description from the generated markdown
def extract_metadata(markdown_text):
    title = ""
    meta_description = ""
    
    lines = markdown_text.split('\n')
    for line in lines:
        line = line.strip()
        if line.lower().startswith("title:"):
            title = line.replace("Title:", "").strip().strip('"')
        elif line.lower().startswith("meta description:"):
            meta_description = line.replace("Meta Description:", "").strip().strip('"')
        
        if title and meta_description:
            break
            
    return title, meta_description

# Add a helper function to get domain from URL
def get_domain(url):
    try:
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        return domain.replace('www.', '')
    except:
        return 'Unknown Source'

# Update the format_time_ago function to handle dates better
def format_time_ago(published_date):
    try:
        if not published_date:
            return "Unknown time"
        
        # Convert the published_date to datetime object
        if isinstance(published_date, str):
            if published_date.endswith('Z'):
                published_time = datetime.strptime(published_date, '%Y-%m-%dT%H:%M:%S.%fZ')
            else:
                published_time = datetime.strptime(published_date, '%Y-%m-%dT%H:%M:%S.%f')
            published_time = published_time.replace(tzinfo=timezone.utc)
        else:
            published_time = published_date
        
        # Get current time in UTC
        now = datetime.now(timezone.utc)
        
        # Calculate the difference
        diff = now - published_time
        
        # Convert to total seconds
        total_seconds = diff.total_seconds()
        
        if total_seconds < 0:
            return "just now"
            
        minutes = total_seconds / 60
        hours = minutes / 60
        days = hours / 24
        
        # More precise time display
        if days >= 1:
            days_int = int(days)
            if days_int == 1:
                return "about 1 day ago"
            return f"about {days_int} days ago"
        elif hours >= 1:
            hours_int = int(hours)
            if hours_int == 1:
                return "about 1 hour ago"
            return f"about {hours_int} hours ago"
        elif minutes >= 1:
            minutes_int = int(minutes)
            if minutes_int == 1:
                return "about 1 minute ago"
            return f"about {minutes_int} minutes ago"
        else:
            return "just now"
    except Exception as e:
        print(f"Error formatting time for date {published_date}: {str(e)}")
        return "Unknown time"

# Function to convert markdown content to WordPress Gutenberg blocks
def convert_to_wordpress_blocks(markdown_content):
    """Convert markdown content to WordPress Gutenberg blocks."""
    # Split content into lines
    lines = markdown_content.split('\n')
    wp_blocks = []
    current_paragraph = []
    metadata = {"title": "", "meta_description": "", "excerpt": ""}
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Handle metadata sections
        if line.startswith('Title:'):
            metadata['title'] = line[6:].strip()
        elif line.startswith('Meta Description:'):
            metadata['meta_description'] = line[16:].strip()
        elif line.startswith('Excerpt:'):
            metadata['excerpt'] = line[8:].strip()
        elif line.startswith('Image Prompt:'):
            wp_blocks.append(f'<!-- wp:paragraph -->\n<p><strong>Image Prompt:</strong> {line[13:].strip()}</p>\n<!-- /wp:paragraph -->')
        elif not line:  # Empty line
            if current_paragraph:
                # Join and wrap the current paragraph
                para_content = ' '.join(current_paragraph)
                # Convert markdown links to WordPress format
                # Match pattern [text](url) and convert to proper WordPress link format
                import re
                def replace_link(match):
                    text = match.group(1)
                    url = match.group(2)
                    return f'<a class="general-link" href="{url}" target="_blank" rel="noopener">{text}</a>'
                
                # First convert any markdown links in the text
                para_content = re.sub(r'\[(.*?)\]\((.*?)\)', replace_link, para_content)
                
                # Then handle the source citations
                para_content = para_content.replace('(Source: ', '(อ้างอิง: <a class="general-link" href="')
                para_content = para_content.replace('(อ้างอิง: ', '(อ้างอิง: <a class="general-link" href="')
                # Make sure we properly close the citation links
                if 'อ้างอิง:' in para_content and not para_content.endswith('</a>)'):
                    parts = para_content.split('" target="_blank" rel="noopener">')
                    if len(parts) > 1:
                        site_name = parts[1].rstrip(')')
                        para_content = f'{parts[0]}" target="_blank" rel="noopener">{site_name}</a>)'
                
                wp_blocks.append(f'<!-- wp:paragraph -->\n<p>{para_content}</p>\n<!-- /wp:paragraph -->')
                current_paragraph = []
        elif line.startswith('# '):  # Title
            wp_blocks.append(f'<!-- wp:heading {"level":1} -->\n<h1 class="wp-block-heading">{line[2:]}</h1>\n<!-- /wp:heading -->')
        elif line.startswith('## '):  # Section heading
            if current_paragraph:
                para_content = ' '.join(current_paragraph)
                # Apply the same link formatting as above
                import re
                def replace_link(match):
                    text = match.group(1)
                    url = match.group(2)
                    return f'<a class="general-link" href="{url}" target="_blank" rel="noopener">{text}</a>'
                
                para_content = re.sub(r'\[(.*?)\]\((.*?)\)', replace_link, para_content)
                para_content = para_content.replace('(Source: ', '(อ้างอิง: <a class="general-link" href="')
                para_content = para_content.replace('(อ้างอิง: ', '(อ้างอิง: <a class="general-link" href="')
                if 'อ้างอิง:' in para_content and not para_content.endswith('</a>)'):
                    parts = para_content.split('" target="_blank" rel="noopener">')
                    if len(parts) > 1:
                        site_name = parts[1].rstrip(')')
                        para_content = f'{parts[0]}" target="_blank" rel="noopener">{site_name}</a>)'
                
                wp_blocks.append(f'<!-- wp:paragraph -->\n<p>{para_content}</p>\n<!-- /wp:paragraph -->')
                current_paragraph = []
            wp_blocks.append(f'<!-- wp:heading -->\n<h2 class="wp-block-heading">{line[3:]}</h2>\n<!-- /wp:heading -->')
        else:
            current_paragraph.append(line)
        i += 1
    
    # Handle any remaining paragraph
    if current_paragraph:
        para_content = ' '.join(current_paragraph)
        # Apply the same link formatting one last time
        import re
        def replace_link(match):
            text = match.group(1)
            url = match.group(2)
            return f'<a class="general-link" href="{url}" target="_blank" rel="noopener">{text}</a>'
        
        para_content = re.sub(r'\[(.*?)\]\((.*?)\)', replace_link, para_content)
        para_content = para_content.replace('(Source: ', '(อ้างอิง: <a class="general-link" href="')
        para_content = para_content.replace('(อ้างอิง: ', '(อ้างอิง: <a class="general-link" href="')
        if 'อ้างอิง:' in para_content and not para_content.endswith('</a>)'):
            parts = para_content.split('" target="_blank" rel="noopener">')
            if len(parts) > 1:
                site_name = parts[1].rstrip(')')
                para_content = f'{parts[0]}" target="_blank" rel="noopener">{site_name}</a>)'
        
        wp_blocks.append(f'<!-- wp:paragraph -->\n<p>{para_content}</p>\n<!-- /wp:paragraph -->')
    
    # Add metadata at the beginning of the output
    metadata_blocks = []
    if metadata['title']:
        metadata_blocks.append(f'<!-- wp:paragraph -->\n<p><strong>Title:</strong> {metadata["title"]}</p>\n<!-- /wp:paragraph -->')
    if metadata['meta_description']:
        metadata_blocks.append(f'<!-- wp:paragraph -->\n<p><strong>Meta Description:</strong> {metadata["meta_description"]}</p>\n<!-- /wp:paragraph -->')
    if metadata['excerpt']:
        metadata_blocks.append(f'<!-- wp:paragraph -->\n<p><strong>Excerpt:</strong> {metadata["excerpt"]}</p>\n<!-- /wp:paragraph -->')
    
    return '\n\n'.join(metadata_blocks + wp_blocks)

# Streamlit App Layout
def main():
    # Initialize session state for search results if not exists
    if 'search_performed' not in st.session_state:
        st.session_state.search_performed = False
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None
    if 'query' not in st.session_state:
        st.session_state.query = "Bitcoin price news"

    st.set_page_config(page_title="Article Generator", layout="wide")
    st.title("Article Generator")
    st.markdown("""
    ### Generate SEO-Optimized Articles from Web Research
    Enter your research query below, specify the number of results and the time frame, and generate an article with Title and Meta Description.
    """)

    # Search input and button in main area
    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        query = st.text_input("Enter your web research query:", st.session_state.query, key="query_input")
        perform_research_button = st.button("Perform Research")

    # Sidebar for search parameters
    st.sidebar.header("Search Parameters")
    
    # Category selection with checkboxes
    st.sidebar.subheader("Content Categories")
    
    # Add 'All' option first
    all_selected = st.sidebar.checkbox("All", value=False, key="category_all")
    
    # Define all categories - removed movies, songs, and github
    categories = {
        "News": "news",
        "Research Papers": "research_paper",
        "Company Info": "company",
        "Tweets": "tweet",
        "Personal Sites": "personal_site",
        "PDFs": "pdf"
    }
    
    # Create checkboxes for each category
    selected_categories = []
    if all_selected:
        selected_categories = ["all"]
        # Disable other checkboxes if 'All' is selected
        for display_name, category in categories.items():
            st.sidebar.checkbox(
                display_name,
                value=True,
                key=f"category_{category}",
                disabled=True
            )
    else:
        for display_name, category in categories.items():
            if st.sidebar.checkbox(display_name, value=category in ["news"], key=f"category_{category}"):
                selected_categories.append(category)
    
    num_results = st.sidebar.number_input(
        "Number of results per category:", 
        min_value=1, 
        max_value=25, 
        value=5,
        help="The total results will be this number multiplied by the number of selected categories"
    )
    
    # Extended Look-Back Window Options
    look_back_options = {
        "2 hours": 2,
        "4 hours": 4,
        "12 hours": 12,
        "1 day": 24,
        "3 days": 72,
        "1 week": 168,
        "2 weeks": 336,
        "1 month": 720,    # 30 days
        "2 months": 1440,  # 60 days
        "3 months": 2160,  # 90 days
        "4 months": 2880,  # 120 days
        "5 months": 3600,  # 150 days
        "6 months": 4320   # 180 days
    }
    
    look_back_label = st.sidebar.selectbox(
        "Select the look-back window:",
        options=list(look_back_options.keys()),
        index=0  # Default to "2 hours"
    )
    hours_back = look_back_options[look_back_label]

    if perform_research_button:
        st.session_state.query = query
        if not query.strip():
            st.error("Please enter a search query.")
            st.stop()
            
        if not selected_categories and not all_selected:
            st.error("Please select at least one category or choose 'All'.")
            st.stop()

        with st.spinner("Performing web research..."):
            try:
                exa_client = initialize_exa()
                search_result = perform_web_research(
                    exa_client, 
                    query, 
                    num_results, 
                    hours_back,
                    selected_categories
                )
                
                if search_result is None:
                    st.stop()
                
                st.session_state.search_results = serialize_search_results(search_result)
                st.session_state.search_performed = True
                
                if not st.session_state.search_results["results"]:
                    st.warning("""
                    No results found. Try:
                    1. Using different search terms
                    2. Extending the time window
                    3. Selecting more categories
                    4. Making the query more general
                    """)
                    st.stop()
                
            except Exception as e:
                st.error(f"""
                Error during research: {str(e)}
                
                Possible solutions:
                1. Check your internet connection
                2. Verify your API key
                3. Try again in a few moments
                4. Reduce the number of results requested
                """)
                st.stop()

    # Display results if search has been performed
    if st.session_state.search_performed and st.session_state.search_results:
        if not st.session_state.search_results["results"]:
            st.warning("No results found for the given query and time frame.")
            st.stop()

        # Display search results with checkbox selection
        st.header("Select Sources to Include in the Article")
        selected_indices = []
        valid_sources = []
        
        for i, res in enumerate(st.session_state.search_results["results"], 1):
            if res.get('text') or res.get('title'):
                title_display = res.get('title', 'Untitled')
                if not title_display or len(title_display.strip()) == 0:
                    title_display = f"Untitled ({res.get('url', 'No URL')})"
                
                # Get domain and time ago
                domain = get_domain(res.get('url', ''))
                time_ago = format_time_ago(res.get('published_date'))
                
                # Format the display string with HTML styling
                styled_source = f"{title_display}\n   <a href='{res.get('url', '')}' style='color: #0969da; text-decoration: none;'>{domain}</a> <span style='color: #666666'>| {time_ago}</span>"
                
                # Use markdown for the styled content
                col1, col2 = st.columns([0.1, 0.9])
                with col1:
                    is_selected = st.checkbox("", value=True, key=f"source_{i}")
                with col2:
                    st.markdown(styled_source, unsafe_allow_html=True)
                
                if is_selected:
                    selected_indices.append(i)
                    valid_sources.append(res)
        
        if not valid_sources:
            st.error("Please select at least one source to generate the article.")
            st.stop()

        # Add a "Generate Article" button after source selection
        generate_article_button = st.button("Generate Article")

        if generate_article_button:
            # Prepare content for GPT
            content = prepare_content_for_gpt(st.session_state.search_results, selected_indices)

            # Generate the article
            with st.spinner("Generating article..."):
                article_markdown, title, meta_description = generate_article(content, st.session_state.query)

            if article_markdown:
                st.success("Article generated successfully!")

                # Display Title and Meta Description
                st.header("Article Metadata")
                st.subheader("Title")
                st.write(title if title else "Not Found")
                st.subheader("Meta Description")
                st.write(meta_description if meta_description else "Not Found")

                # Display the markdown content
                st.header("Generated Markdown Article")
                st.markdown(article_markdown)

                # Add collapsible source content - using st.session_state.search_results instead
                with st.expander("View Source Content"):
                    st.json(st.session_state.search_results)

                # Provide a copyable text area for the markdown
                st.subheader("Copy the Markdown:")
                st.text_area("Markdown Output", value=article_markdown, height=300)

                # Provide download button
                st.download_button(
                    label="Download Markdown",
                    data=article_markdown,
                    file_name=f"article_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                    mime="text/markdown",
                )

                # Convert markdown to WordPress Gutenberg blocks
                wordpress_blocks = convert_to_wordpress_blocks(article_markdown)

                # Display WordPress Gutenberg blocks
                st.header("WordPress Gutenberg Blocks")
                st.code(wordpress_blocks)

                # Provide download button for WordPress Gutenberg blocks
                st.download_button(
                    label="Download WordPress Gutenberg Blocks",
                    data=wordpress_blocks,
                    file_name=f"wordpress_blocks_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                    mime="text/plain",
                )
            else:
                st.error("Failed to generate the article. Please try again.")

if __name__ == "__main__":
    main()