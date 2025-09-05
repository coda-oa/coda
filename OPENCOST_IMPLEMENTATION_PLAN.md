# OpenCost Reporting Feature Implementation Plan

## Overview

Implementation plan for adding OpenCost metadata export functionality to CODA. OpenCost is a standardized XML format for exchanging publication cost data, enabling transparency in scholarly publishing costs.

## Goals

- Export CODA publication and contract data in OpenCost XML format
- Create and save OpenCost reports for institutions
- Support both individual publications and bulk exports
- Maintain data integrity and validation according to OpenCost schema

## **LLM Context: Problem Domain & Key Insights** 🤖

*This section provides comprehensive context for future LLM assistance on this project.*

### **Project Background**

- **CODA**: Django-based system for managing publication costs, contracts, and institutional data
- **OpenCost**: XML schema standard for exchanging publication cost data between institutions
- **Goal**: Export CODA data in OpenCost XML format for institutional transparency and reporting

### **Critical Domain Understanding**

#### **OpenCost Schema Scope**

- **Publications**: Support `external_costsplitting` boolean field for multi-institutional cost sharing
- **Contracts**: Do NOT support cost splitting (confirmed via XSD analysis)
- **Institution Identifiers**: ROR, ISNI, Ringold supported in schema
- **Contract Identifiers**: ESAC (primary), OAI, EZB, local (secondary) supported
- **Date Formats**: Flexible YYYY, YYYY-MM, YYYY-MM-DD support required

#### **CODA Architecture Insights**

- **Invoice Bounded Context**: All cost management happens here, not in Publication domain
- **Domain-Driven Design**: Separate domain models from Django models with transformation layers
- **Link Pattern**: Existing flexible identifier system for publications serves as template
- **Cost Types**: Separate `PublicationCostType` and `ContractCostType` enums already OpenCost-compliant

#### **Key Technical Decisions Made**

1. **Cost Splitting is Publication-Only**: OpenCost XSD confirms no cost splitting for contracts
2. **Invoice Context for Cost Data**: Cost splitting belongs with positions, not publications themselves
3. **Future-Proof Identifiers**: Use type/value pattern like CODA's Link system for extensibility
4. **Multi-Institutional Support**: Beyond binary splitting - track specific amounts per institution

### **Architecture Patterns to Follow**

#### **Domain Model Structure**

```python
# Example of CODA's pattern - Domain model separate from Django
@dataclass(slots=True, frozen=True, kw_only=True)
class PublicationCostSharingArrangement:
    shares: list[InstitutionCostShare]
    # Rich domain behavior methods here
```

#### **Identifier System Pattern**

```python
# Follow CODA's Link pattern for maximum flexibility
class InstitutionIdentifier(models.Model):
    institution = models.ForeignKey(Institution, related_name="identifiers")
    type = models.CharField(max_length=50)  # No enum - fully flexible
    value = models.CharField(max_length=255)
```

### **Common Pitfalls to Avoid**

- ❌ Adding cost splitting to contract positions (OpenCost doesn't support it)
- ❌ Storing cost splitting data in Publication model (belongs in invoice context)
- ❌ Using rigid enums for identifier types (prevents future OpenCost evolution)
- ❌ Assuming simple boolean for cost splitting (users need detailed financial tracking)

### **Integration Points**

- **Existing CODA Models**: Publication, Contract, Institution, Invoice, Position
- **Domain Models**: `/app/src/coda/domain/opencost/` already implemented
- **Pattern Consistency**: Follow CODA's Link system for new identifier models
- **Data Transformation**: Domain models ↔ Django models ↔ OpenCost XML

### **Validation Requirements**

- Cost sharing amounts must sum to position total
- Only publication positions can have cost sharing
- Institution identifiers must follow OpenCost type constraints
- Contract invoice groups need unique IDs within contract scope

### **User Experience Considerations**

- Users want detailed financial breakdown, not just "split/not split"
- Administrative interface needed for managing identifier types
- Cost sharing UI should validate totals in real-time
- Export should handle missing data gracefully (OpenCost has many optional fields)

### **Files to Reference for Context**

- **OpenCost Schema**: `/app/src/coda/domain/opencost/opencost.xsd`
- **OpenCost Docs**: `/app/src/coda/domain/opencost/opencost_docs.md`
- **CODA Invoice Domain**: `/app/src/coda/domain/invoice.py`
- **CODA Link Pattern**: `/app/src/coda/apps/publications/models/_link.py`
- **Existing Domain Models**: `/app/src/coda/domain/opencost/_*.py`

### **Conversation Evolution & Key Insights**

#### **Major Architectural Realizations**

1. **Cost Splitting Complexity**: Started with simple boolean, evolved to understand users need detailed multi-institutional financial tracking
2. **Domain Boundary Respect**: Realized cost splitting belongs in invoice bounded context, not publication domain
3. **OpenCost Schema Analysis**: Discovered cost splitting only applies to publications, not contracts (confirmed via XSD)
4. **Future-Proofing Need**: Identifier systems must accommodate future OpenCost schema evolution without database changes

#### **Decision Evolution Timeline**

- **Initial**: Simple boolean `external_cost_splitting` field on Publication
- **Correction 1**: Move to invoice context (proper bounded context)
- **Correction 2**: Multi-institutional support with specific amounts
- **Final**: Publication-only cost sharing with detailed financial tracking

#### **Critical Schema Understanding**

- OpenCost XSD line 23: `external_costsplitting` only in `publication_type`, not `contract_type`
- Users need "which institutions pay how much" not just "is split or not"
- CODA's existing cost type enums already match OpenCost requirements perfectly

#### **Implementation Readiness Checklist**

- ✅ OpenCost schema requirements understood
- ✅ CODA architecture patterns identified
- ✅ Data model gaps analyzed
- ✅ Future-proof identifier system designed
- ✅ Cost splitting complexity properly scoped
- ✅ Domain boundaries respected
- 🚧 Ready for Phase 1.1 implementation

## **Implementation Roadmap**

### **Phase 1: Data Model Enhancements** ⭐ *Start Here*

**Objective**: Add missing data models using future-proof identifier patterns
**Duration**: 1-2 sprints
**Status**: Ready to begin

#### **1.1 Critical Foundation Models**

- **Institution Identifiers**: Flexible system for ROR, ISNI, Ringold IDs
- **Contract Identifiers**: ESAC, OAI, EZB, local identifier support
- **Invoice Groups**: Contract invoice grouping with periods
- **Cost Splitting**: Multi-institutional publication cost sharing with detailed financial tracking

#### **1.2 Data Enhancement Tasks**

- **Publication-Contract Linking**: Group-based linking for invoice periods
- **Flexible Date Support**: YYYY, YYYY-MM, YYYY-MM-DD formats
- **VAT Handling**: Dual VAT approach support

---

### **Phase 2: Service Layer Development**

**Objective**: Build transformation services and validation logic
**Duration**: 2-3 sprints

#### **2.1 Core Services**

- **Data Transformation**: CODA → OpenCost mapping
- **Validation Engine**: OpenCost schema compliance
- **Data Aggregation**: Contract and publication grouping

---

### **Phase 3: Export Engine Implementation**

**Objective**: Create XML generation and data aggregation engines with web viewing capability
**Duration**: 2-3 sprints

#### **3.1 Export Features**

- **XML Generation**: Standards-compliant OpenCost output
- **Report Storage**: Database persistence for generated reports
- **Report Management**: Create, view, download, and regenerate reports
- **Web Interface**: HTML display of report content and metadata
- **Download Options**: XML file download functionality

#### **3.2 Report Model Structure - Interactive Web Reports**

**Design Philosophy**: Store both XML content for download AND relational links for interactive web viewing

```python
class OpenCostReport(models.Model):
    """Stored OpenCost reports for web viewing and download"""
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)  # e.g., "2024 Annual Report"
    report_period_start = models.DateField()
    report_period_end = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(User, on_delete=models.CASCADE)
    xml_content = models.TextField()  # Store the OpenCost XML for download
    summary_stats = models.JSONField()  # Publication/contract counts, totals

    class Meta:
        ordering = ['-generated_at']

class OpenCostReportPublication(models.Model):
    """Links publications included in an OpenCost report"""
    report = models.ForeignKey(OpenCostReport, on_delete=models.CASCADE, related_name="publications")
    publication = models.ForeignKey('publications.Publication', on_delete=models.CASCADE)
    cost_total = models.DecimalField(max_digits=20, decimal_places=4)
    currency = models.CharField(max_length=3)
    has_cost_splitting = models.BooleanField()

    class Meta:
        unique_together = ('report', 'publication')

class OpenCostReportContract(models.Model):
    """Links contracts included in an OpenCost report"""
    report = models.ForeignKey(OpenCostReport, on_delete=models.CASCADE, related_name="contracts")
    contract = models.ForeignKey('contracts.Contract', on_delete=models.CASCADE)
    cost_total = models.DecimalField(max_digits=20, decimal_places=4)
    currency = models.CharField(max_length=3)
    invoice_count = models.IntegerField()

    class Meta:
        unique_together = ('report', 'contract')

class OpenCostReportInvoice(models.Model):
    """Links invoices included in an OpenCost report"""
    report = models.ForeignKey(OpenCostReport, on_delete=models.CASCADE, related_name="invoices")
    invoice = models.ForeignKey('invoices.Invoice', on_delete=models.CASCADE)
    # Link to publication or contract
    publication = models.ForeignKey('publications.Publication', on_delete=models.CASCADE, null=True, blank=True)
    contract = models.ForeignKey('contracts.Contract', on_delete=models.CASCADE, null=True, blank=True)

    class Meta:
        unique_together = ('report', 'invoice')
        constraints = [
            models.CheckConstraint(
                check=(
                    models.Q(publication__isnull=False, contract__isnull=True) |
                    models.Q(publication__isnull=True, contract__isnull=False)
                ),
                name='invoice_belongs_to_publication_or_contract'
            )
        ]
```

**Benefits of Relational Report Storage**:
- ✅ **Interactive Navigation**: Click publications/contracts/invoices → detailed CODA pages
- ✅ **Performance**: Pre-computed cost totals and statistics for fast web display
- ✅ **Data Integrity**: Links maintained even if underlying data changes
- ✅ **Flexible Views**: Filter, sort, and search within reports
- ✅ **Audit Trail**: Track which exact objects were included in each report
- ✅ **XML Availability**: Still provides downloadable OpenCost XML for external systems

---

### **Phase 4: User Interface & API**

**Objective**: Build Django views, templates, and web interfaces for OpenCost reporting
**Duration**: 2-3 sprints

#### **4.1 Web Interface Features**

- **Report Dashboard**: List of generated OpenCost reports with summaries and statistics
- **Report Generation Form**: User interface to create new reports with date ranges and filters
- **Interactive Report Viewer**:
  - Tabbed interface (Publications, Contracts, Summary)
  - Clickable publications → publication detail pages
  - Clickable contracts → contract detail pages
  - Clickable invoices → invoice detail pages
  - Cost breakdown tables with filtering and sorting
- **Download Interface**: XML file download with proper content-type headers
- **Report Management**: Edit report metadata, regenerate reports when data changes

#### **4.2 User Experience Flow**

1. **Generate Report**: User selects date range and clicks "Generate OpenCost Report"
2. **Processing**: System creates XML, stores relational data, shows progress
3. **Interactive Report View**:
   - Summary tab with statistics and totals
   - Publications tab with clickable links to publication details
   - Contracts tab with clickable links to contract details
   - Cost breakdown with drill-down capabilities
4. **Navigation**: Click any publication/contract/invoice to view detailed CODA pages
5. **Download**: User can download XML file for external systems
6. **Management**: List of historical reports with regeneration options

#### **4.3 Template Structure**

```html
<!-- OpenCost Report Viewer Template -->
<div class="opencost-report">
  <header>
    <h1>{{ report.title }}</h1>
    <p>Period: {{ report.period_start }} - {{ report.period_end }}</p>
    <a href="{% url 'opencost:download' report.pk %}" class="btn">Download XML</a>
  </header>

  <nav class="report-tabs">
    <button data-tab="summary">Summary</button>
    <button data-tab="publications">Publications ({{ report.publications.count }})</button>
    <button data-tab="contracts">Contracts ({{ report.contracts.count }})</button>
  </nav>

  <div id="publications-tab">
    {% for report_pub in report.publications.all %}
      <div class="publication-row">
        <a href="{% url 'publications:detail' report_pub.publication.pk %}">
          {{ report_pub.publication.title }}
        </a>
        <span class="cost">{{ report_pub.cost_total }} {{ report_pub.currency }}</span>
        {% if report_pub.has_cost_splitting %}<span class="badge">Cost Shared</span>{% endif %}
      </div>
    {% endfor %}
  </div>
</div>
```

---

### **Phase 5: Advanced Features**

**Objective**: Data validation, quality checks, and advanced reporting features
**Duration**: 1-2 sprints

#### **5.1 Data Quality & Validation**

- **OpenCost Readiness Checker**: Dashboard showing data completeness for OpenCost export
- **Missing Data Reports**: Identify publications/contracts lacking required identifiers
- **Validation Rules**: Pre-export checks for OpenCost schema compliance
- **Data Quality Metrics**: Statistics on identifier coverage, cost completeness

#### **5.2 Advanced Features**

- **Report Templates**: Predefined report configurations for common use cases
- **Bulk Operations**: Mass assignment of identifiers, cost sharing arrangements
- **Export Scheduling**: Optional automated report generation (future enhancement)

---

### **Phase 6: Testing & Documentation**

**Objective**: Comprehensive testing and user documentation
**Duration**: 1 sprint

## **Phase 1 Detailed Implementation** 🚀

### **1.1 Institution Identifiers (Future-Proof Design)**

**Task**: Create flexible institution identifier system
**Files**: New models extending institution system
**Pattern**: Follow CODA's Link pattern for maximum extensibility

#### **Recommended Approach: Dedicated InstitutionIdentifier Model**

```python
class InstitutionIdentifier(models.Model):
    """Flexible institution identifiers - future-proof design"""
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name="identifiers")
    type = models.CharField(max_length=50)  # ror, isni, ringold, local, etc.
    value = models.CharField(max_length=255)

    class Meta:
        unique_together = ('institution', 'type')

    def __str__(self):
        return f"{self.institution.name} - {self.type}: {self.value}"
```

**Benefits**:

- ✅ **Zero schema changes** for new OpenCost identifier types
- ✅ **Simple querying**: `institution.identifiers.filter(type='ror')`
- ✅ **Type safety**: Consistent with CODA patterns
- ✅ **Performance**: Direct foreign key relationships

### **1.2 Contract Identifiers (Future-Proof Design)**

**Task**: Create flexible contract identifier system
**Files**: New models for contract identifiers
**Pattern**: Mirror Institution identifier approach

```python
class ContractIdentifier(models.Model):
    """Flexible contract identifiers - future-proof design"""
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="identifiers")
    type = models.CharField(max_length=50)  # esac, oai, ezb, local, etc.
    value = models.CharField(max_length=255)

    class Meta:
        unique_together = ('contract', 'type')

    def __str__(self):
        return f"{self.contract.title} - {self.type}: {self.value}"
```

### **1.3 Multi-Institution Cost Sharing (Publication-Only)**

**Task**: Create comprehensive cost-sharing system for publication cost sharing
**Files**: New models for institutional cost sharing in invoice bounded context
**Understanding**: CODA users need to track which institutions pay how much for publication positions. OpenCost only supports cost splitting for publications, not contracts.

#### **Domain Models for Publication Cost Sharing**

```python
# New domain model: /app/src/coda/domain/invoice.py
@dataclass(slots=True, frozen=True, kw_only=True)
class InstitutionCostShare:
    """Represents one institution's share of a publication position's cost"""
    institution_id: int  # Reference to Institution
    amount: Money
    cost_type: PublicationCostType  # Only publications support cost sharing
    percentage: Decimal | None = None  # Optional percentage for validation

@dataclass(slots=True, frozen=True, kw_only=True)
class PublicationCostSharingArrangement:
    """Collection of institutional cost shares for a publication position"""
    shares: list[InstitutionCostShare]

    def total_amount(self) -> Money:
        """Sum of all institutional shares"""
        if not self.shares:
            return Money("0", Currency.EUR)
        currency = self.shares[0].amount.currency
        return sum((share.amount for share in self.shares), Money("0", currency))

    def is_complete_split(self, position_cost: Money) -> bool:
        """Verify that shares sum to position total"""
        return self.total_amount() == position_cost

    def participating_institutions(self) -> list[int]:
        """Get list of institution IDs involved in cost sharing"""
        return [share.institution_id for share in self.shares]

# Enhanced Position (Publication only) with cost sharing
@dataclass(slots=True, frozen=True, kw_only=True)
class Position(CommonPosition[PublicationItemType, PublicationCostType]):
    item: PublicationItemType
    cost_type: PublicationCostType
    cost_sharing: PublicationCostSharingArrangement | None = None  # Only for publications

    def has_external_cost_splitting(self) -> bool | None:
        """OpenCost external_costsplitting derived from cost_sharing"""
        if self.cost_sharing is None:
            return None  # Unknown
        return len(self.cost_sharing.shares) > 1  # True if multiple institutions

# ContractPosition remains unchanged (no cost sharing)
@dataclass(slots=True, frozen=True, kw_only=True)
class ContractPosition(CommonPosition[ContractYear, ContractCostType]):
    item: ContractYear
    cost_type: ContractCostType
    # No cost_sharing field - contracts don't support cost splitting in OpenCost
```

#### **Django Models for Publication Cost Sharing**

```python
# New models: /app/src/coda/apps/invoices/models.py
class PublicationPositionCostShare(models.Model):
    """Individual institution's share of a publication position's cost"""
    position = models.ForeignKey(
        Position,
        on_delete=models.CASCADE,
        related_name="publication_cost_shares",
        limit_choices_to={'publication__isnull': False}  # Only publication positions
    )
    institution = models.ForeignKey('institutions.Institution', on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=20, decimal_places=4)
    currency = models.CharField(max_length=3)
    cost_type = models.CharField(max_length=255)  # PublicationCostType only
    percentage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ('position', 'institution')
        constraints = [
            models.CheckConstraint(
                check=models.Q(position__publication__isnull=False),
                name='cost_sharing_publication_only'
            )
        ]

    def __str__(self):
        return f"{self.institution.name}: {self.amount} {self.currency}"

# Enhanced Position model (only for publication positions)
class Position(models.Model):
    # ... existing fields ...

    def get_publication_cost_sharing(self) -> PublicationCostSharingArrangement | None:
        """Convert Django cost shares to domain model (publications only)"""
        if not self.publication or not self.publication_cost_shares.exists():
            return None

        shares = [
            InstitutionCostShare(
                institution_id=share.institution_id,
                amount=Money(share.amount, Currency[share.currency]),
                cost_type=PublicationCostType(share.cost_type),
                percentage=share.percentage
            )
            for share in self.publication_cost_shares.all()
        ]
        return PublicationCostSharingArrangement(shares=shares)

    def has_external_cost_splitting(self) -> bool | None:
        """OpenCost external_costsplitting derived property (publications only)"""
        if not self.publication:
            return None  # Not applicable to contract positions
        arrangement = self.get_publication_cost_sharing()
        if arrangement is None:
            return None  # Unknown
        return len(arrangement.shares) > 1
```

#### **User Interface Considerations**

```python
# Cost sharing form/formset (publication positions only)
class PublicationCostShareForm(forms.ModelForm):
    class Meta:
        model = PublicationPositionCostShare
        fields = ['institution', 'amount', 'percentage']

PublicationCostSharingFormSet = forms.inlineformset_factory(
    Position,
    PublicationPositionCostShare,
    form=PublicationCostShareForm,
    extra=1,
    can_delete=True
)
```

**Benefits of This Publication-Focused Approach**:

- ✅ **OpenCost Compliant**: Aligns exactly with OpenCost schema (publication-only)
- ✅ **Domain Accurate**: Reflects the actual business logic of cost splitting
- ✅ **Simplified Implementation**: No need to handle contract cost sharing edge cases
- ✅ **Clear Semantics**: Cost sharing applies to individual publication payments
- ✅ **User-Friendly**: Intuitive UI that matches the OpenCost export behavior
- ✅ **Data Integrity**: Database constraints ensure cost sharing only for publications

**Future Extensions**:

- Cost sharing templates for common arrangements
- Automatic percentage calculation from amounts
- Integration with institutional reporting dashboards
- Historical cost sharing analysis

### **1.4 Contract Invoice Groups (New Model)**

**Task**: Create model for OpenCost contract invoice grouping concept
**Files**: New ContractInvoiceGroup model

```python
class ContractInvoiceGroup(models.Model):
    """Groups contract invoices by period for OpenCost reporting"""
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="invoice_groups")
    group_id = models.CharField(max_length=100)  # Unique within contract
    period_start = models.DateField()
    period_end = models.DateField()

    class Meta:
        unique_together = ('contract', 'group_id')

    def __str__(self):
        return f"{self.contract.title} - Group {self.group_id} ({self.period_start} to {self.period_end})"

# Link invoices to groups
class InvoiceGroupMembership(models.Model):
    """Links invoices to contract invoice groups"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    group = models.ForeignKey(ContractInvoiceGroup, on_delete=models.CASCADE)

    class Meta:
        unique_together = ('invoice', 'group')
```

**New Models**:

```python
class ContractIdentifierType(models.Model):
    """Dynamic identifier types - no enum constraints"""
    name = models.CharField(max_length=255, unique=True)
    is_primary = models.BooleanField(default=False)  # For OpenCost primary vs secondary
    description = models.TextField(blank=True)

    def __str__(self) -> str:
        return self.name

class ContractIdentifier(models.Model):
    """Flexible type/value pairs like Link system"""
    contract = models.ForeignKey(Contract, on_delete=models.CASCADE, related_name="identifiers")
    type = models.ForeignKey(ContractIdentifierType, on_delete=models.CASCADE)
    value = models.CharField(max_length=255)

    class Meta:
        unique_together = ('contract', 'type', 'value')

    def __str__(self) -> str:
        return f"{self.type.name}: {self.value}"
```

**Benefits**:

- ✅ **Zero schema changes** for new OpenCost identifier types
- ✅ **Admin interface** can manage identifier types
- ✅ **Database seeding** for current OpenCost types (ESAC, OAI, EZB, local)
- ✅ **Future OpenCost versions** supported automatically
- ✅ **Custom institutional identifiers** supported
- ✅ **Type safety** in domain layer with fallback patterns

**Domain Layer Integration**:

```python
# Similar to Link system - typed classes + flexible fallback
class EsacIdentifier:
    def __init__(self, value: str): ...
    def type(self) -> str: return "ESAC"

class ContractUserIdentifier:  # Like UserLink
    def __init__(self, id_type: str, value: str): ...

def create_contract_identifier(id_type: str, value: str) -> ContractIdentifier:
    # Pattern matching like create_link()
```

**Migration Strategy**:

```python
# Seed initial OpenCost identifier types
def seed_opencost_identifier_types():
    types = [
        ("ESAC", True, "ESAC Initiative identifier"),
        ("oai", False, "OAI identifier"),
        ("ezb", False, "EZB identifier"),
        ("local", False, "Local institution identifier"),
    ]
    for name, is_primary, desc in types:
        ContractIdentifierType.objects.get_or_create(
            name=name, defaults={"is_primary": is_primary, "description": desc}
        )
```

## **Next Steps & Deliverables**

### **Immediate Action Items** 🎯

1. **Create Phase 1.1 Models** (Priority: Critical)
   - [ ] `InstitutionIdentifier` model
   - [ ] `ContractIdentifier` model
   - [ ] `ContractInvoiceGroup` model
   - [ ] `InvoiceGroupMembership` model
   - [ ] `PublicationPositionCostShare` model for multi-institutional publication cost sharing
   - [ ] `InstitutionCostShare` and `PublicationCostSharingArrangement` domain models
   - [ ] Enhanced `Position` domain model with publication cost sharing support
   - [ ] `OpenCostReport` model and related relational models for interactive web viewing
     - [ ] `OpenCostReportPublication` for clickable publication links
     - [ ] `OpenCostReportContract` for clickable contract links
     - [ ] `OpenCostReportInvoice` for clickable invoice links

2. **Database Migration** (Priority: High)
   - [ ] Generate Django migrations for new models and fields
   - [ ] Test migrations on development data
   - [ ] Update admin interface for new models
   - [ ] Add data validation for cost sharing arrangements

3. **Service Layer Foundation** (Priority: Medium)
   - [ ] Create `/app/src/coda/apps/opencost/services/` directory
   - [ ] Implement basic transformation services
   - [ ] Add data validation logic for cost sharing

### **Key Technical Decisions Made** ✅

- **Future-proof identifier system**: Using type/value pattern like CODA's Link system
- **Dedicated models**: Separate `InstitutionIdentifier` and `ContractIdentifier` models
- **Zero schema changes**: New identifier types require no database changes
- **Existing cost types**: Confirmed CODA's cost type system already supports OpenCost requirements

### **Critical Dependencies**

1. **OpenCost Schema**: `/app/src/coda/domain/opencost/` (✅ Ready)
2. **CODA Models**: Contract, Publication, Institution, Invoice (✅ Ready)
3. **Database**: PostgreSQL with Django ORM (✅ Ready)
4. **Phase 1.1 Completion**: Required before any transformation logic

### **Success Metrics**

- [ ] All Phase 1.1 models implemented and tested
- [ ] Zero breaking changes to existing CODA functionality
- [ ] Future OpenCost identifier types supported without schema changes
- [ ] Admin interface allows manual identifier management
- [ ] Ready for Phase 2 transformation service development

---

*This implementation plan follows CODA's established patterns and ensures the OpenCost reporting feature integrates seamlessly with the existing system while providing a future-proof foundation for identifier management.*

## **Technical Considerations**

### **Performance**

- Use bulk queries for large reports
- Cache XML generation for large reports
- Consider async processing for very large exports

### **Data Quality**

- Validate institution identifiers
- Handle missing DOIs gracefully
- Ensure cost data consistency

### **Extensibility**

- Design for additional export formats
- Support custom report filters
- Enable report templates

---

## **🎯 Complete Implementation Strategy - Ready to Execute!**

### **Export & Reporting Strategy - Finalized ✅**

- **Generation**: On-demand report creation (primarily yearly, flexible timing)
- **Storage**: Database persistence with `OpenCostReport` model for audit trails
- **Web Interface**: HTML viewing of report content and metadata
- **Download**: XML file download for external system integration
- **Management**: List, view, regenerate reports through web interface

### **All Requirements Clarified ✅**

1. ✅ **Institution Identifiers**: Starting fresh (no existing data migration)
2. ✅ **User Permissions**: Single-institution deployment (no cross-institutional concerns)
3. ✅ **Contract Invoice Groups**: OpenCost billing period grouping requirements understood
4. ✅ **Export Strategy**: On-demand generation with web viewing and database storage

### **Technical Foundation Ready ✅**

- **Data Models**: Future-proof identifier system following CODA's Link pattern
- **Domain Architecture**: Respects bounded contexts, cost splitting publication-only
- **OpenCost Compliance**: Schema requirements fully analyzed and incorporated
- **User Experience**: Complete report generation and viewing workflow defined

**Status**: 📋 Planning phase complete - Ready for Phase 1.1 implementation
**Next Step**: Begin Phase 1.1 - Data Model Enhancements
**Last Updated**: September 5, 2025
