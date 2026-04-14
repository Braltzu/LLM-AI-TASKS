"""
Demo 8 – Resumable AI Procurement Agent (LangGraph Persistence + Interrupt)

Scenario: An AI agent handles purchase requests. When a purchase exceeds
€10,000 it must pause for manager approval — which may come hours or days later.

The graph:

  START → lookup_vendors → fetch_pricing → compare_quotes
        → request_approval (INTERRUPTS here — process exits!)
        → submit_purchase_order → notify_employee → END

To simulate a real-world "late second invocation" across process restarts,
we use SqliteSaver (file-based checkpoint) and two CLI modes:

  python demo8.1-purchase-agent.py              # First run  — steps 1-3, then suspends
  python demo8.1-purchase-agent.py --resume     # Second run — manager approves, steps 5-6

Between the two runs the Python process exits completely.  The full agent
state (vendor data, pricing, chosen quote) survives on disk in SQLite.
"""

#KATSE TÄNNE

#Joutui muiden taskien takia muokkaamaan koodia sen verran
#että osa muutoksista on kadonnut iteraatioiden mukana.
#Myös se että en huomioinut tehdä välitallennuksia koodeista
#missä toimivat taskit yksitellen niin tässä suorituksessa
#kaikki 4 Taskiin asti yhdessä.

#VOI KATSOA MUUALLE


import sys
import re
import os
import sqlite3
import time
from typing import Annotated, TypedDict
import requests
import logging

from langchain_core.tools import tool
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import interrupt, Command
from langchain_google_genai import ChatGoogleGenerativeAI

# ─── State ────────────────────────────────────────────────────────────────────

class ProcurementState(TypedDict):
    request: str
    quantity: int
    vendors: list[dict]
    quotes: list[dict]
    best_quote: dict
    approval_status: str
    po_number: str
    notification: str
    item_type: str


# ─── LLM (used only for the notification step to make it feel "agentic") ─────

llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")


# ─── Node functions ──────────────────────────────────────────────────────────

def lookup_vendors(state: ProcurementState) -> dict:
    """Step 1: Fetch live product data from API."""
    print("\n[Step 1] Fetching live product data from dummyjson...")
    url = "https://dummyjson.com/products/category/laptops"
    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        products = response.json().get("products", [])
        print(f"   Found {len(products)} products from API.")
        return {"vendors": products}
    except Exception as e:
        logging.warning(f"   API Error: {e}. Using fallback.")
        fallback = [{"title": "Fallback Business Laptop", "price": 899.0, "stock": 100, "shippingInformation": "Ships in 1 week", "brand": "Generic Fallback"}]
        return {"vendors": fallback}



#Task 1 part of it atleast...
#Tämä nyt teki mitä vaadittiinkin eli laski tilattujen laitteiden summan ja lähetti siitä siitä imnoituksen managerille aina.
"""
def get_unit_price(vendor: str) -> float:
    
    Gets the unit price for a given vendor's laptops.
    This is a mock tool and returns a hardcoded price.
    
    print(f"    |_ Tool: getting price for {vendor}...")
    time.sleep(0.5)  # simulate API call
    if "dell" in vendor.lower():
        return 248.0
    elif "lenovo" in vendor.lower():
        return 235.0
    elif "hp" in vendor.lower():
        return 259.0
    else:
        return 9999.0
"""

def fetch_pricing(state: ProcurementState) -> dict:
    """Step 2: Find cheapest product with <2 weeks delivery and calculate total."""
    print("\n[Step 2] Finding cheapest product and calculating total...")
    
    request_text = state.get("request", "")
    match = re.search(r'(\d+)', request_text)
    quantity = int(match.group(1)) if match else 1
    print(f"   Parsed quantity: {quantity}")

    products = state.get("vendors", [])
    
    # Filter for stock > 0 and availability within 2 weeks
    available_products = []
    for p in products:
        if p.get("stock", 0) > 0:
            ship_info = p.get("shippingInformation", "").lower()
            # Dummyjson uses shipping strings like "Ships in 1 month", "Ships in 1 week"
            if "month" not in ship_info and "years" not in ship_info:
                available_products.append(p)
    
    if not available_products:
        logging.warning("   No products available within 2 weeks. Falling back to all in-stock.")
        available_products = [p for p in products if p.get("stock", 0) > 0]
        
    if not available_products:
        available_products = [{"title": "Emergency Fallback Laptop", "price": 999.0, "brand": "Generic Fallback"}]

    # Find cheapest
    cheapest = min(available_products, key=lambda x: x.get("price", 9999.0))
    unit_price = float(cheapest.get("price", 0.0))
    product_name = cheapest.get("title", "Unknown Laptop")
    vendor_name = cheapest.get("brand", "Unknown Vendor")
    total_price = unit_price * quantity
    
    best_quote = {
        "vendor": vendor_name,
        "product_name": product_name,
        "unit_price": unit_price,
        "total": total_price,
        "delivery_days": 14
    }
    
    print(f"   Selected: {product_name} by {vendor_name} at €{unit_price:,.2f}/unit")
    print(f"   Total for {quantity}: €{total_price:,.2f}")

    return {
        "quantity": quantity,
        "best_quote": best_quote,
        "quotes": [best_quote]
    }








def compare_quotes(state: ProcurementState) -> dict:
    """Step 3: Compare quotes and pick the best one."""
    print("\n[Step 3] Comparing quotes...")
    time.sleep(0.5)
    # Since fetch_pricing already picked the best one from the API, we just pass it
    best = state["best_quote"]
    print(f"   Best quote: {best['vendor']} ({best.get('product_name', '')}) at €{best['total']:,.2f}")
    return {"best_quote": best}




#Task 2 interrupt if price over 10k€
def should_request_approval(state: ProcurementState) -> str:
    """Decide whether to request approval or skip straight to ordering."""
    best_total = state["best_quote"]["total"]
    if best_total > 10000:
        print(f"   Total €{best_total:,.2f} exceeds €10,000 threshold. Routing for approval.")
        return "request_approval"
    else:
        print(f"   Total €{best_total:,.2f} is within budget. Auto-approving and skipping to purchase.")
        return "submit_purchase_order"
    




def request_approval(state: ProcurementState) -> dict:
    """Step 4: Human-in-the-loop — request manager approval for orders > €10,000."""
    best = state["best_quote"]
    quantity = state["quantity"]
    print("\n[Step 4] Order exceeds €10,000 — manager approval required!")
    print(f"   Sending approval request to manager...")
    amount_str = f"€{best['total']:,.2f}"
    delivery_str = f"{best['delivery_days']} business days"
    print(f"   ┌─────────────────────────────────────────────┐")
    print(f"   │  APPROVAL NEEDED                            │")
    print(f"   │  Vendor:   {best['vendor']:<33}│")
    print(f"   │  Product:  {best.get('product_name', 'Laptop')[:33]:<33}│")
    print(f"   │  Amount:   {amount_str:<33}│")
    print(f"   │  Items:    {quantity} units                         │")
    print(f"   │  Delivery: {delivery_str:<33}│")
    print(f"   └─────────────────────────────────────────────┘")

    # ── THIS IS WHERE THE MAGIC HAPPENS ──
    # interrupt() freezes the entire graph state into the checkpoint store.
    # The process can now exit completely. When resumed later (even days later),
    # execution continues right here with the resume value.
    decision = interrupt({
        "message": f"Approve purchase of {quantity} x {best.get('product_name', 'laptops')} from {best['vendor']} for €{best['total']:,.2f}?",
        "vendor": best["vendor"],
        "amount": best["total"],
    })

    print(f"\n[Step 4] Manager responded: {decision}")
    return {"approval_status": decision}





def submit_purchase_order(state: ProcurementState) -> dict:
    """Step 5: Submit the purchase order to the ERP system."""
    if "reject" in state["approval_status"].lower():
        print("\n[Step 5] Purchase REJECTED by manager. Aborting.")
        return {"po_number": "REJECTED"}

    print("\n[Step 5] Submitting purchase order to ERP system...")
    time.sleep(1)
    po_number = "PO-2026-00342"
    print(f"   Purchase order created: {po_number}")
    print(f"   Vendor: {state['best_quote']['vendor']}")
    print(f"   Product: {state['best_quote'].get('product_name', 'Laptop')}")
    print(f"   Amount: €{state['best_quote']['total']:,.2f}")
    return {"po_number": po_number}



#TASK 3 Denial Routing---------------------------
#Proper routing if approval = rejected
def reititys(state: ProcurementState) -> dict:
    status = state["approval_status"]

    if "reject" in status.lower():
        return "notify_employee"
    else:
        return "submit_purchase_order"
#---------------------------------------------- 




def notify_employee(state: ProcurementState) -> dict:
    """Step 6: Use LLM to draft and send a notification to the employee."""
    print("\n[Step 6] Notifying employee...")

    if "reject" in state["approval_status"].lower():
        prompt = (
            f"Write a brief, professional notification (2-3 sentences) to an employee "
            f"that their purchase request for 50 laptops was rejected by the manager. "
            f"Be empathetic but concise."
        )
    else:
        prompt = (
            f"Write a brief, professional notification (2-3 sentences) to an employee "
            f"that their purchase request has been approved and processed. "
            f"Details: {state['quantity']} x {state['best_quote'].get('product_name', 'laptops')} from {state['best_quote']['vendor']}, "
            f"€{state['best_quote']['total']:,.2f}, PO number {state['po_number']}, "
            f"delivery in {state['best_quote']['delivery_days']} business days."
        )

    response = llm.invoke(prompt)
    notification = response.content
    print(f"   Employee notification sent:")
    print(f"   \"{notification}\"")
    return {"notification": notification}
#----------------------------------------------------------------------------------------------------------




# ─── Build the graph ─────────────────────────────────────────────────────────
#
#   START → lookup_vendors → fetch_pricing → compare_quotes
#         → request_approval (INTERRUPT)
#         → submit_purchase_order → notify_employee → END

builder = StateGraph(ProcurementState)

builder.add_node("lookup_vendors", lookup_vendors)
builder.add_node("fetch_pricing", fetch_pricing)
builder.add_node("compare_quotes", compare_quotes)
builder.add_node("request_approval", request_approval)
builder.add_node("submit_purchase_order", submit_purchase_order)
builder.add_node("notify_employee", notify_employee)

builder.add_edge(START, "lookup_vendors")
builder.add_edge("lookup_vendors", "fetch_pricing")
builder.add_edge("fetch_pricing", "compare_quotes")
# builder.add_edge("compare_quotes", "request_approval") # This was the old direct edge
builder.add_conditional_edges(
    "compare_quotes",
    should_request_approval,
    {"request_approval": "request_approval", "submit_purchase_order": "submit_purchase_order"}
)
#builder.add_edge("request_approval", "submit_purchase_order")
builder.add_conditional_edges("request_approval", 
                              reititys, 
                              {"submit_purchase_order": "submit_purchase_order", "notify_employee": "notify_employee"})
builder.add_edge("submit_purchase_order", "notify_employee")
builder.add_edge("notify_employee", END)





# ─── Checkpointer (SQLite — survives process restarts!) ──────────────────────

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "procurement_checkpoints.db")
THREAD_ID = "procurement-thread-1"
config = {"configurable": {"thread_id": THREAD_ID}}


# ─── Main ────────────────────────────────────────────────────────────────────

def run_first_invocation(graph):
    """First run: employee submits request, agent does steps 1-3, then suspends."""
    print("=" * 60)
    print("  FIRST INVOCATION — Employee submits purchase request")
    print("=" * 60)
    print("\nEmployee request: \"Order 50 laptops for the sales team\"")

    result = graph.invoke(
        {"request": "Order 50 laptops for the sales team"},
        config,
    )

    # After interrupt, the graph returns with __interrupt__ info
    print("\n" + "=" * 60)
    print("AGENT SUSPENDED — waiting for manager approval")
    print("=" * 60)
    print("\n  The agent process can now exit completely.")
    print("  All state (vendors, pricing, best quote) is frozen in SQLite.")
    print(f"  Checkpoint DB: {DB_PATH}")
    print(f"  Thread ID: {THREAD_ID}")
    print("\n  In a real system, the manager gets a Slack/email notification.")
    print("  They might respond hours or even days later.\n")
    print("  To resume, run:")
    print(f"    python {os.path.basename(__file__)} --resume\n")






def run_second_invocation(graph):
    """Second run: manager approves, agent wakes up at step 5 with full context."""
    print("=" * 60)
    print("  SECOND INVOCATION — Manager approves (maybe days later!)")
    print("=" * 60)

    # Show that the state survived the process restart
    saved_state = graph.get_state(config)
    if not saved_state or not saved_state.values:
        print("\nNo saved state found! Run without --resume first.")
        return

    print("\nLoading state from checkpoint...")
    print(f"  ✓ Request: {saved_state.values.get('request', 'N/A')}")
    print(f"  ✓ Vendors found: {len(saved_state.values.get('vendors', []))}")
    print(f"  ✓ Quantity: {saved_state.values.get('quantity', 'N/A')}")
    print(f"  ✓ Quotes received: {len(saved_state.values.get('quotes', []))}")
    best = saved_state.values.get("best_quote", {})
    print(f"  ✓ Best quote: {best.get('vendor', 'N/A')} at €{best.get('total', 0):,.2f}")
    print(f"\n  Steps 1-3 are NOT re-executed — their output is in the checkpoint!\n")

    # Resume with the manager's approval
    print("Manager clicks [APPROVE] ...")
    time.sleep(1)

    result = graph.invoke(
        Command(resume="Approved — go ahead with the purchase."),
        #Command(resume="Rejected — over budget."),
        config,
    )

    print("\n" + "=" * 60)
    print("PROCUREMENT COMPLETE")
    print("=" * 60)
    print(f"\n  PO Number:    {result.get('po_number', 'N/A')}")
    print(f"  Vendor:       {result.get('best_quote', {}).get('vendor', 'N/A')}")
    print(f"  Total:        €{result.get('best_quote', {}).get('total', 0):,.2f}")
    print(f"  Approval:     {result.get('approval_status', 'N/A')}")
    print()






if __name__ == "__main__":
    resume_mode = "--resume" in sys.argv

    # Clean start if not resuming
    if not resume_mode and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"(Cleaned up old checkpoint DB)")

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    checkpointer = SqliteSaver(conn)
    graph = builder.compile(checkpointer=checkpointer)

    try:
        if resume_mode:
            run_second_invocation(graph)
        else:
            run_first_invocation(graph)
    finally:
        conn.close()
